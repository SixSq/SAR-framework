"""
This module provides methods to access and request SlipStream Service-Offers
and also S3 buckets. The API and library used are respectively 'CIMI' and Boto.
"""

from log import get_logger

logger = get_logger(name='lib-data-access')


def _url(endpoint):
    return endpoint + '/api/service-offer?$filter='


def _request_url(api, resources):
    return _url(api.endpoint) + resources[0:len(resources) - 4]


def _check_str_list(data):
    if isinstance(data, unicode) or isinstance(data, str):
        data = [data]
    return data


def _join_attributes(attr, operator):
    attr = _check_str_list(attr)
    return (' ' + operator + ' ').join(attr)


def _format_data_resource(data):
    # data = _check_str_list(data)
    return (["resource:class='%s.SAFE'" % prod.strip() for prod in data])


def request_data(api, specs, data):
    """
    :param   specs: Specs used as filter to narrpw specifically the 'DATA' service-offer
    :type

    :param   specs: uri of the bucket
    :type
    """
    specs_resource = _join_attributes(specs, 'and')
    data_resource = _format_data_resource(data)

    resources = ""
    for p in data_resource:
        temp = _join_attributes([p, specs_resource], 'and')
        resources = _join_attributes([temp, resources], 'or')
    request = _request_url(api, resources)
    logger.info('request_data: %s' % request)
    return api.session.get(request).json()


def request_vm(api, specs, clouds, orderby=True):
    specs_resource = _join_attributes(specs, 'and')
    resources = ""
    # clouds      = _check_str_list(clouds)
    for c in clouds:
        temp = _join_attributes([c, specs_resource], 'and')
        resources = _join_attributes([temp, resources], 'or')
    request = _request_url(api, resources)
    if orderby:
        request += '&$orderby=price:unitCost'
    logger.info('request_vm: %s' % request)
    return api.session.get(request).json()


if __name__ == '__main__':
    specs = ["resource:type='DATA'", "resource:platform='S3'"]

    prd_list = ['S1A_IW_GRDH_1SDV_20151226T182813_20151226T182838_009217_00D48F_5D5F',
                'S1A_IW_GRDH_1SDV_20160424T182813_20160424T182838_010967_010769_AA98',
                'S1A_IW_GRDH_1SDV_20160518T182817_20160518T182842_011317_011291_936E',
                'S1A_IW_GRDH_1SDV_20160611T182819_20160611T182844_011667_011DC0_391B',
                'S1A_IW_GRDH_1SDV_20160705T182820_20160705T182845_012017_0128E1_D4EE',
                'S1A_IW_GRDH_1SDV_20160729T182822_20160729T182847_012367_013456_E8BF',
                'S1A_IW_GRDH_1SDV_20160822T182823_20160822T182848_012717_013FFE_90AF',
                'S1A_IW_GRDH_1SDV_20160915T182824_20160915T182849_013067_014B77_1FCD']
