from django.db import models
from pylogix import PLC
import numpy as np


def cell7validation(points):
    prev_time = 0
    for i, [hour, minute] in enumerate(points):

        if hour == 0 and minute == 0 and i != 0:  # zero row found, i.e. end of data found
            for [h, m] in points[i:]:  # verify that there are no data points after zero row
                if h != 0 or m != 0:
                    return False
            return True

        if minute < 0 or minute > 59:  # minute out of range
            return False

        cur_time = hour + (minute/60)
        if prev_time >= cur_time:
            return False
        prev_time = cur_time

    return True


def cell7postupload(points):
    end = len(points)
    for i, [h, m] in enumerate(points):
        if h == 0 and m == 0 and i != 0:
            end = i
            break

    cd = CellData()
    ch, cm = points[end-1]
    plus_twenty = int(cm) + 20
    complete_hours = ch + (plus_twenty // 60)
    complete_minutes = plus_twenty % 60

    with PLC() as comm:
        comm.IPAddress = cd.get_ip("cell7")
        comm.Write('Total_Auto_Samples', end)
        comm.Write('Test_Complete_Hours', complete_hours)
        comm.Write('Test_Complete_Minutes', complete_minutes)
        comm.Write('FAL_Control_hours.LEN', end)
        comm.Write('FAL_Control_minutes.LEN', end)


class CellData(models.Model):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cells = {
            'cell7': {
                'columns': ('Hours', 'Minutes'),
                'tagnames': ('Time_Hours', 'Time_Minutes'),
                'common_name': "Cell 7",
                'ip': '192.168.10.17',
                'link': "/upload/cell7",
                'max input': 12,
                'validation': cell7validation,
                'post_upload': cell7postupload,
            },
            'cell8': {
                'columns': ('Main Motor Test Points', 'Load Motor Test Points', 'Pressure Test Points'),
                'tagnames': ('MainMotorTestPoints', 'LoadMotorTestPoints', 'PressureTestPoints'),
                'common_name': "Cell 8",
                'ip': '192.168.10.10',
                'link': "/upload/cell8",
                'max input': 600,
            },

        }

    def get_context(self, cellname):
        """
        Returns the template context
        :param cellname:
        :return:
        """
        context = {'cellname': cellname}
        for key in ('columns', 'common_name'):
            context[key] = self.cells[cellname][key]
        return context

    def get_ip(self, cellname):
        """
        Returns the ip of the cell's PLC
        :param cellname:
        :return:
        """
        return self.cells[cellname]['ip']

    def cell_list(self):
        """
        Returns the context for the index page that lists the cells
        :return:
        """
        cell_list = []
        for k, v in self.cells.items():
            cell_list.append({
                'name': k,
                'link': v['link'],
                'common_name': v['common_name']
            })
        return {'cells': cell_list}

    def tag_names(self, cellname):
        return self.cells[cellname]['tagnames']

    def max_input(self, cellname):
        return self.cells[cellname]['max input']

    def validation(self, cellname):
        """
        Return the validation function for cell if present, otherwise return always true function
        :param cellname: cell to provide validation function for
        :return: function for validation
        """
        celldata = self.cells[cellname]
        if 'validation' in celldata:
            return celldata['validation']
        return lambda *x: True

    def post_upload(self, cellname):
        """
        Return the post upload function for cell if present, otherwise returns useless function
        :param cellname: cell to provide post upload function for
        :return: function for post upload
        """
        celldata = self.cells[cellname]
        if 'post_upload' in celldata:
            return celldata['post_upload']
        return lambda *x: None


def upload_points(points, cellname):
    cd = CellData()

    with PLC() as comm:
        comm.IPAddress = cd.get_ip(cellname)
        for c, data in zip(cd.tag_names(cellname), np.array(points).T):
            comm.Write(c, [0] * CellData().max_input(cellname))
            comm.Write(c, list(data))
    cd.post_upload(cellname)(points)


def parse_points(points, cellname):
    points = points.replace('""', '0')
    points = points.replace('"', '')

    if not isinstance(points, str):
        return None
    if len(points) == 0:
        return None

    points_new = []
    for inner in points[2:-2].split('],['):
        row = inner.split(',')
        row = [int(item) for item in row]
        points_new.append(row)

    if len(points_new) > CellData().max_input(cellname):
        return None

    if CellData().validation(cellname)(points_new):
        return points_new


def get_points(cellname: str):
    cd = CellData()
    max_input = cd.max_input(cellname)

    with PLC() as comm:
        comm.IPAddress = cd.get_ip(cellname)
        col_data = []
        for c in cd.tag_names(cellname):
            ret = comm.Read(c, max_input)
            col_data.append(ret.Value)
    points = []

    end = max_input + 1
    for i, row in enumerate(reversed(list(zip(*col_data)))):
        if sum(row) != 0:
            end = max_input-i
            break

    for i, row in enumerate(zip(*col_data)):
        if i == end:
            break
        points.append(list(row))
    return points

