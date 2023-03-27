from django.shortcuts import render
from .models import upload_points, CellData, parse_points, get_points
from django.http import JsonResponse
import logging
import datetime

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


def index(request):
    context = CellData().cell_list()
    return render(request, 'upload.html', context)


def error(request, cellname, message=None):
    if isinstance(message, str):
        messages = [message]
    elif isinstance(message, list):
        messages = message
    else:
        messages = ["Unknown error occurred"]

    logger.warning(", ".join(messages), {
        'action': 'upload',
        'cellname': cellname,
        'ip': get_client_ip(request)
    })

    return render(request, 'error_upload.html', {'messages': messages})


def cell(request, cellname):
    # request will be POST if the user just submitted the form
    if request.method == 'POST':
        try:
            cleaned = parse_points(request.POST['data'], cellname)
            if cleaned is None:
                return error(request, cellname, "Invalid data entered (1)")
            upload_points(cleaned, cellname)

            ip = get_client_ip(request)
            logger.info(f'{datetime.datetime.now()}: {cellname} test points uploaded by {ip}', {
                'action': 'upload',
                'cellname': cellname,
                'ip': ip,
            })
        except IOError as e:
            print(e)
            return error(request, cellname, "Invalid data entered (2)")
    return render(request, 'cellupload.html', CellData().get_context(cellname))


def readpoints(request, cellname):
    return JsonResponse({cellname: get_points(cellname)}, safe=False)
