import datetime
from django.shortcuts import render
from django.http import HttpResponse
from .models import Exporter
from django.template import loader
from .forms import DateForm
import requests
import logging

logger = logging.getLogger(__name__)


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if 'HTTP_X_REAL_IP' in request.META:
        _ip = request.META['HTTP_X_REAL_IP']
    elif x_forwarded_for:
        _ip = x_forwarded_for.split(',')[0]
    else:
        _ip = request.META.get('REMOTE_ADDR')
    return _ip


def error(request, cellname, message=None):
    if isinstance(message, str):
        messages = [message]
    elif isinstance(message, list):
        messages = message
    else:
        messages = ["Unknown error occurred"]

    logger.warning(", ".join(messages), {
        'action': 'download',
        'cellname': cellname,
        'ip': get_client_ip(request)
    })

    template = loader.get_template('error.html')
    return HttpResponse(template.render({'messages': messages}, request))


def index(request):
    template = loader.get_template('index.html')

    context = {
        'cells': [
            {
                "name": "cell5",
                'common_name': "Cell 5"
            },
            {
                "name": "cell7",
                'common_name': "Cell 7"
            },
            {
                "name": "tribology",
                'common_name': "Tribology Lab"
            },
        ]
    }
    return HttpResponse(template.render(context, request))


def cell(request, cellname):
    # request will be POST if the user just submitted the form
    if request.method == 'POST':
        # create a form instance and populate it with data from the request:
        form = DateForm(request.POST)

        # check whether it's valid:
        if form.is_valid():
            date = form.cleaned_data['date']  # datetime object
            exporter = Exporter()
            try:
                # specifically unwrapping datetime object here and re wrapping it in the method so that the user input
                # gets cleaned a bit and will cause an error if something weird gets through instead of being injectable
                df = exporter.get_day(date.day, date.month, date.year, cellname)
            except requests.exceptions.ConnectionError as e:
                return error(request, cellname, f"Connection error occurred with database. Please contact site admin. {e}")
            except Exception as e:
                return error(request, cellname, f"Unknown error occurred. {e}")
            finally:
                exporter.close()  # always close your connections!

            if df is None:
                exporter.close()
                return error(request, cellname, f'No data available for that day ({date.month}/{date.day}/{date.year}).')
            # df = exporter.cell7convert(df)  # special cell 7 conversions

            response = HttpResponse(df.to_csv(), content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename=cell7_{date.month}-{date.day}-{date.year}.csv'

            # response = HttpResponse(content_type='text/csv')
            # response['Content-Disposition'] = f'attachment; filename=cell7_{date.month}-{date.day}-{date.year}.csv'
            # df.to_csv(path_or_buf=response)  # for some reason pandas can write directly to a download buffer

            ip = get_client_ip(request)
            logger.info(str(datetime.datetime.now()) +
                        f' {cellname} download for {date.month}/{date.day}/{date.year} requested by {ip}',
                        {
                            'action': 'download',
                            'cellname': cellname,
                            'ip': ip
                        })

            return response
        else:
            return error(request, cellname, 'Invalid date. Please use format: M/D/YYYY.')

    # if request is GET we send the normal page
    else:
        form = DateForm()
        return render(request, 'cell.html', {'form': form, 'cellname': cellname})
