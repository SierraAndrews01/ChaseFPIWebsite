import datetime
import pandas as pd
from django.db import models
from influxdb import InfluxDBClient
import numpy as np
from dateutil import tz


class Exporter(models.Model):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = None

        """
        The dictionary below `cellconfig` defines what data to grab where it is and how to process it for each possible
        export. Here is a list of the attributes: 
        'database' is the database from the server to grab the data from,
        'host' (optional) is the server to grab from, defaults to localhost
        'measurements' is a tuple of what measurements in the influxdb database to pull data from
        'postprocess' (optional) is a function reference to any specific post processing that needs to be done
        """

        self.cellconfig = {
            'cell7': {
                'database': 'cell7',
                'postprocess': self.cell7convert,
                'measurements': ('PLC_Tags', 'TE', 'Trident')
            },
            'tribology': {
                'database': 'data',
                'host': '10.253.3.20',
                'measurements': ('TE',)
            },
            'cell5': {
                'database': 'cell5',
                'postprocess': self.cell5convert,
                'measurements': ('data1', 'data2')
            }
        }

    def get_day(self, day, month, year, cellname) -> pd.DataFrame:
        """
        Queries the specified test for exactly one day of data. Auto formats as needed.
        :param cellname: name of configuration to use, check the list in the constructor
        :return: dataframe of day of data requested
        """
        if cellname not in self.cellconfig:
            raise NotImplemented(f"Support for {cellname} not implemented.")
        config = self.cellconfig[cellname]

        # get host from config, if no host use default connection
        if 'host' not in config:
            host = '192.168.10.102'
        else:
            host = config['host']

        self.client = InfluxDBClient(host=host, port=8086, username='readonly', password='readonly', timeout=20)
        self.client.switch_database(config['database'])

        timezone = tz.gettz('America/Chicago')
        todays_date = datetime.datetime(year, month, day, tzinfo=timezone)
        start_stamp = int(todays_date.timestamp()) * 1_000_000_000
        stop_date = todays_date + datetime.timedelta(days=1)
        stop_stamp = int(stop_date.timestamp()) * 1_000_000_000
        data = []
        for measurement in config['measurements']:
            query = f"select * from {measurement} where time > {start_stamp} and time < {stop_stamp}"

            r = self.client.query(query)
            if len(r) > 0:
                df = pd.DataFrame(r.items()[0][1])  # convert result to dataframe

                # if the time ends exactly with zero nanoseconds the conversion does not work.
                # So we check the rows and add the .000000Z to any row that needs it.
                # for some godforsaken reason the '.' character needs to be escaped, ignore the warning.
                mask = ~df.time.str.contains('\.')
                df.time.values[mask] = df.time[mask].str[:-1] + '.000000Z'
                df.index = pd.DatetimeIndex(pd.to_datetime(df.time, format="%Y-%m-%dT%H:%M:%S.%fZ") - datetime.timedelta(hours=6))

                data.append(df)  # add to running list of data

        self.client.close()  # close client to prevent memory leaks
        self.client = None
        if len(data) > 0:  # make sure there is data before continuing
            if len(data) > 1:  # if more than one table was read
                # check if any overlap in columns names between tables
                cols = [col for dataframe in data for col in dataframe.columns]

                # everyone has 'time' column, it comes free with your fucking xbox
                cols = list(filter(lambda c: c != "time", cols))
                if len(set(cols)) != len(cols):
                    for i, dataframe in enumerate(data):
                        # rename all columns with measurement name appended except time column
                        dataframe.columns = [f"{col}_{config['measurements'][i]}" if col != 'time' else col for col in dataframe.columns]

                data = pd.concat(data)  # combine all results from all queries
            sorted_data = data.sort_index()

            # If this configuration has special post-processing to perform, do it before returning dataframe
            if 'postprocess' in config:
                return config['postprocess'](sorted_data)
            else:
                return sorted_data

    def close(self):
        """
        This exists so the connection can be closed if there is an error, get_day closes the connection at the end
        but not when there is an error.
        """
        if self.client is not None:
            self.client.close()

    def cell7convert(self, df: pd.DataFrame) -> pd.DataFrame:
        # Lists of the columns from each table that we use.
        trident_cols = ["oil_rh", "s0_magnitude", "s0_phase", "s0_temp_post_ref", "s0_temp_post_sample", "s1_magnitude",
                        "s1_phase", "s1_temp_post_ref", "s1_temp_post_sample", "s2_magnitude", "s2_phase",
                        "s2_temp_post_sample", "s3_magnitude", "s3_phase", "s3_temp_post_sample", "s4_magnitude",
                        "s4_phase", "s4_temp_post_sample", "sweep_count"]
        te_cols = ["Density (dm/cc)", "Dialectric constant (-)", "Resistance (Ohms)", "Temperature (C)",
                   "Viscosity (cp)"]
        main_cols = ['time', 'Air_Flow_MLPM', 'Oil_Temp_F', 'Oil_Temp_Cooler_In_F', 'Press_System_PSI',
                     'Water_Valve_CMD', 'Water_Flow_In_GPM', 'Water_Temp_In_F', "Hours_Counter.ACC",
                     "Minutes_Counter.ACC", "Seconds_Counter.ACC"]
        # this column was added so if the day requested is a while ago it won't exist
        if "Water_Temp_Out_F" in df.columns:
            main_cols.append("Water_Temp_Out_F")

        # Check if the columns from TE and Trident are available in the dataframe.
        te_present = True
        for te_col in te_cols:
            if te_col not in df.columns:
                te_present = False
                break
        trident_present = True
        for tr_col in trident_cols:
            if tr_col not in df.columns:
                trident_present = False
                break

        # Sum together the columns for each sensor that is present to be flexible if a sensor is not being used.
        columns_needed = main_cols
        if trident_present:
            columns_needed += trident_cols
        if te_present:
            columns_needed += te_cols

        # Index the original dataframe with these columns to drop the columns we won't use.
        df2 = df[columns_needed]

        # very complex way of trimming out parts when the test is not running
        good_rows = df.Testing_HMI == 1
        on = df.Testing_HMI[0] == True
        for i in range(len(df.Testing_HMI)):
            row = df.Testing_HMI[i]
            if on and row == False:
                on = False
            elif on:
                good_rows[i] = True
            elif row == True:
                on = True
                good_rows[i] = True
        df2 = df2[good_rows]

        # resample with rate of 100s (approx rate of the trident sensor)
        df2 = df2.resample("100S").mean(numeric_only=True).dropna(how='all')

        # add test elapse time column
        df2['Elapse Hours'] = df2["Hours_Counter.ACC"] + df2["Minutes_Counter.ACC"] / 60 + df2["Seconds_Counter.ACC"] / 3600

        df2 = df2[['Elapse Hours'] + df2.columns.tolist()[:-1]]  # move elapse to first column

        # this whole block here is to fill in the time when the plc is not logging but is still running
        in_nan_range = False
        last = start = 0
        for i in range(1, len(df2['Elapse Hours'])):
            v = df2['Elapse Hours'][i]
            if not in_nan_range and np.isnan(v):
                in_nan_range = True
                start = i
                if i != 1:
                    last = df2['Elapse Hours'][i - 1]
            elif in_nan_range and not np.isnan(v):
                in_nan_range = False
                df2['Elapse Hours'][start - 1:i + 1] = np.linspace(last, df2['Elapse Hours'][i], i - start + 2)

        # drop the other time columns
        df2.drop(["Hours_Counter.ACC", "Minutes_Counter.ACC", "Seconds_Counter.ACC"], axis=1, inplace=True)

        df2.fillna(method='ffill', inplace=True)  # fill the nan values with the previous valid value
        return df2

    def cell5convert(self, df):
        # resample with rate of 45s (approx rate of the trident sensor)
        df2 = df.resample("45S").mean(numeric_only=True).dropna(how='all')
        return df2