"""
This module provides methods to access and request SlipStream Service-Offers
and also S3 buckets. The API and library used are respectively 'CIMI' and Boto.
"""

from log import get_logger

logger = get_logger(name='lib-data-access')


def _url(endpoint):
    return endpoint + '/api/service-offer?$filter='


def _request_url(api, cimi_filter):
    return _url(api.endpoint) + cimi_filter


def _join_attributes(attr, operator):
    return (' ' + operator + ' ').join(attr)


def _to_data_resource(data):
    return ["resource:class='%s.SAFE'" % prod.strip() for prod in data]


def request_data(api, product_list):
    specs = ["resource:type='DATA'", "resource:platform='S3'"]
    base_data_spec = _join_attributes(specs, 'and')
    product_list = _to_data_resource(product_list)

    cimi_filter = base_data_spec
    if product_list:
        cimi_filter = cimi_filter + ' and (' + ' or '.join(product_list) + ')'
    request = _request_url(api, cimi_filter)
    logger.info('request_data: %s' % request)
    return api.session.get(request).json()


def request_vm(api, specs, clouds, orderby=True):
    specs.append("resource:operatingSystem='linux'")
    base_specs = _join_attributes(specs, 'and')
    cimi_filter = base_specs
    if clouds:
        cimi_filter = cimi_filter + ' and (' + ' or '.join(clouds) + ')'
    request = _request_url(api, cimi_filter)
    if orderby:
        request += '&$orderby=price:unitCost'
    logger.info('request_vm: %s' % request)
    resp = api.session.get(request).json()
    return resp


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
