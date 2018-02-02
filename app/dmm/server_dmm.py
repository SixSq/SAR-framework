import sys
import os
import time
import traceback

from ConfigParser import SafeConfigParser

from flask import Flask, request, Response, send_from_directory
from elasticsearch import Elasticsearch
from slipstream.api import Api
import boto
import boto.s3.connection
import requests
from datetime import datetime
from threading import Thread

import lib_access as sc
import decision_making_module as dmm
import summarizer as summarizer
from log import get_logger

logger = get_logger(name='dmm-server')

CONFIG_FILE = 'dmm.conf'

config_parser = None

app = Flask(__name__, static_url_path='')
api = Api()
elastic_host = 'http://localhost:9200'
doc_type = 'eo-proc'
server_host = 'localhost'
res = Elasticsearch([{'host': 'localhost', 'port': 9200}])


@app.route('/')
def root():
    with open('media/index.html') as fd:
        return Response(fd.read(), status=200)


@app.route('/media/<path:path>')
def send_media(path):
    return send_from_directory('media', path)


def connect_s3():
    access_key = s3_credentials[2]
    secret_key = s3_credentials[3]
    host = s3_credentials[0]

    return boto.connect_s3(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        host=host,
        # is_secure=False,               # uncomment if you are not using ssl
        calling_format=boto.s3.connection.OrdinaryCallingFormat())


def _format_specs(specs):
    for k, v in specs.items():
        specs[k][0] = ("resource:vcpu='%d'" % v[0])
        specs[k][1] = ("resource:ram>'%d'" % int(v[1] - 1))
        specs[k][2] = ("resource:disk>'%d'" % int(v[2] - 1))
    return specs


# def get_vm_specs(id):
#     json = api.cimi_get(id).json
#     spec_keys = ['id',
#                  'resource:vcpu',
#                  'resource:ram',
#                  'resource:disk']
#     # 'resource:typeDisk'] Maybe SSD boost the process
#     return [v for k, v in json.items() if k in spec_keys]


def download_product(bucket_id, output_id):
    """
    :param   bucket_id: uri of the bucket
    :type    bucket_id: str

    :param   conn: interface to s3 bucket
    :type    conn: boto connect_s3 object

    param    output_id: product id
    type     output_id: str
    """
    conn = connect_s3()
    bucket = conn.get_bucket(bucket_id)
    key = bucket.get_key(output_id)
    output_path = os.getcwd() + output_id
    key.get_contents_to_filename(output_path)

    logger.info("Product stored @ %s." % output_id)


def cancel_deployment(deployment_id):
    api.terminate(deployment_id)
    state = api.get_deployment(deployment_id)[2]
    while state != 'cancelled':
        logger.info("Terminating deployment %s." % deployment_id)
        time.sleep(5)
        api.terminate(deployment_id)


def watch_execution_time(start_time):
    time_format = '%Y-%m-%d %H:%M:%S.%f UTC'
    delta = datetime.utcnow() - datetime.strptime(start_time,
                                                  time_format)
    execution_time = delta.seconds
    return (execution_time)


def wait_product(deployment_id, cloud, offer, time_limit):
    """
    :param   deployment_id: uuid of the deployment
    :type    deployment_id: str
    """
    deployment_data = api.get_deployment(deployment_id)
    state = deployment_data[2]
    output_id = ""
    state_final = 'ready'

    while state != state_final and not output_id:
        deployment_data = api.get_deployment(deployment_id)
        logger.info('Deployment data: %s' % deployment_data)
        t = watch_execution_time(deployment_data[3])
        logger.info("Deployment '%s' in state '%s' (waiting for %s). Time elapsed: %s seconds" %
                    (deployment_id, state, state_final, t))
        logger.info("SLA time bound left: %d" % (int(time_limit) - int(t)))
        if (t >= time_limit) or (state == ("cancelled" or "aborted")):
            cancel_deployment(deployment_id)
            return ("SLA time bound exceeded. Deployment is cancelled.")

        time.sleep(45)
        state = deployment_data[2]
        output_id = deployment_data[8].split('/')[-1]

    download_product(s3_credentials[1], output_id)
    summarizer.summarize_run(deployment_id, cloud, offer, ss_username, ss_password)

    return "Product %s delivered!" % output_id


def _all_products_on_cloud(c, rep_so, prod_list):
    products_cloud = ['xXX' for so in rep_so if so['connector']['href'] == c]

    return len(products_cloud) >= len(prod_list)


def _check_str_list(data):
    if isinstance(data, unicode) or isinstance(data, str):
        data = [data]
    return data


def find_data_loc(prod_list):
    """
    :param   prod_list: Input product list
    :type    prod_list: list

    :param   cloud_legit: Data localization found on service catalog
    :type    cloud_legit: dictionnary
    """
    prod_list = _check_str_list(prod_list)
    specs_data = ["resource:type='DATA'", "resource:platform='S3'"]
    rep_so = sc.request_data(api, specs_data, prod_list)['serviceOffers']
    cloud_set = list(set([c['connector']['href'] for c in rep_so]))
    cloud_legit = []
    for c in cloud_set:
        if _all_products_on_cloud(c, rep_so, prod_list):
            cloud_legit.append(c)
    _check_str_list(cloud_legit)
    return cloud_legit


def _schema_validation(reqs):
    """Validates if SLA and results store coordinates are provided with the request.
    reqs: {'SLA': {}, 'result': {}}
    dict('SLA')    = {'requirements':['time', 'price', 'resolution'], 'product_list':['prod_list']}
    dict('result') = {'s3_credentials':[host, bucket, api-key, secret_key]}
    """
    if "SLA" not in reqs:
        raise ValueError("No 'SLA' in given data")
    if "result" not in reqs:
        raise ValueError("No 'result' in given data")
    for k, v in reqs.items():
        if not isinstance(v, dict):
            raise ValueError("%s is not a dict in given data" % k)

    sla = reqs['SLA']

    if "product_list" not in sla:
        raise ValueError("Missing product list in given SLA data")
    if "requirements" not in sla:
        raise ValueError("Missing requirements in given SLA data")

    for k, v in reqs['SLA'].items():
        if not isinstance(v, list):
            raise ValueError("%s is not a list in given data" % k)

    return True


def populate_db(index, id=""):
    if not id:
        rep = res.indices.create(index=index, ignore=400)
        logger.info("Create index %s" % index)
    else:
        rep = res.index(index=index,
                        doc_type="eo-proc",
                        id=id,
                        body={})
        logger.info("Create document %s: " % id)
    return rep


def run_benchmarks(clouds, specs_vm, product_list, offer):
    index = 'sar'
    req_index = requests.get(elastic_host + '/' + index)
    if not req_index:
        populate_db(index)

    deployments = []
    for c in clouds:
        populate_db(index, c)
        service_offers = _components_service_offers(c, specs_vm)
        deployment_id = deploy_run(c, product_list, service_offers, offer, 9999)
        logger.info("Deployed run: %s on cloud %s with service offers %s" %
                    (deployment_id, c, str(service_offers)))
        deployments.append(deployment_id)
    return deployments


def _check_BDB_cloud(index, clouds):
    valid_cloud = []
    for c in _check_str_list(clouds):
        req = '/'.join([index, doc_type, c])
        rep = _get_elastic(req).json()
        if rep['found']:
            valid_cloud.append(c)

    if not valid_cloud:
        raise ValueError("Benchmark DB has no logs for %s go use "
                         "POST on `SLA_INIT` to initialize." % clouds)
    return valid_cloud


def _get_elastic(index=""):
    return requests.get(elastic_host + '/' + index)


def _check_BDB_state():
    if not _get_elastic():
        raise ValueError("Benchmark DB down!")
    return True


def _check_BDB_index(index):
    _check_BDB_state()
    rep_index = _get_elastic(index)
    if (not rep_index) or (len(rep_index.json()) < 1):
        raise ValueError("Empty Benchmark DB please use POST on `SLA_INIT` \
                                        to initialize the system")
    return True


def _components_service_offers(cloud, specs):
    cloud = [("connector/href='%s'" % cloud)]
    service_offers = {'mapper':
                          sc.request_vm(api, specs['mapper'],
                                        cloud)['serviceOffers'][0]['id'],
                      'reducer':
                          sc.request_vm(api, specs['reducer'],
                                        cloud)['serviceOffers'][0]['id']}
    return service_offers


def deploy_run(cloud, product, service_offers, offer, timeout):
    server_ip = config_get('dmm_ip')
    server_hostname = config_get('dmm_hostname')
    mapper_so = service_offers['mapper']
    reducer_so = service_offers['reducer']

    if mapper_so and reducer_so:
        proc_module = config_get('ss_module_proc_sar')
        comps_clouds = {'mapper': cloud, 'reducer': cloud}
        # FIXME: need to provide user's S3 endpoint, bucket and creds for results.
        comps_params = {'mapper': {'service-offer': mapper_so,
                                   'product-list': ' '.join(product),
                                   'server_hn': server_hostname,
                                   'server_ip': server_ip},
                        'reducer': {'service-offer': reducer_so,
                                    'server_hn': server_hostname,
                                    'server_ip': server_ip}}
        comps_counts = {'mapper': len(product),
                        'reducer': 1}
        logger.info('Deploying: on "%s" with params "%s" and multiplicity "%s".' %
                    (comps_clouds, comps_params, comps_counts))
        deployment_id = api.deploy(proc_module,
                                   cloud=comps_clouds,
                                   parameters=comps_params,
                                   multiplicity=comps_counts,
                                   tags='EOproc',
                                   keep_running='never')
        daemon_watcher = Thread(target=wait_product, args=(deployment_id, cloud,
                                                           offer, timeout))
        daemon_watcher.setDaemon(True)
        daemon_watcher.start()
        return '%s/run/%s' % (api.endpoint, deployment_id)
    else:
        msg = "No suitable instance types found for mapper and reducer on cloud %s" % cloud
        logger.warn(msg)
        return msg


def get_user_connectors(user):
    cloud_set = api.get_user(user).configured_clouds
    return list(cloud_set)


@app.errorhandler(500)
def internal_error(exception):
    logger.error(traceback.format_exc())
    msg = 'Internal server error.'
    resp = Response(msg, status=500, mimetype='plain/text')
    return resp


@app.route('/cost', methods=['GET'])
def sla_cost():
    data_admin = {}
    for c in get_user_connectors(ss_username):
        req = '/'.join([elastic_host, 'sar', doc_type, c])
        item = requests.get(req).json()
        logger.info(item)
        if item.get('status') != 200:
            error_msg = 'Failed getting data from backend.'
            error = {'error': error_msg, 'reason': item['error']['reason']}
            logger.warn(error)
            return Response(error_msg, status=500)
        if item['found']:
            logger.info('SLA cost found item: %' % item)
            item = item['_source']
            for k, v in item.items():
                specs = _format_specs(v['components'])
                ids = _components_service_offers(c, specs)
                item[k]['price'] = dmm.get_price(ids.values(), v['time_records'])
        data_admin[c] = item

    resp = Response(data_admin, status=200, mimetype='application/json')
    return resp


''' initialization by the system admin :

    : Inputs specs and products

    : Verify if the DB is running
    : Find the connector to cloud where the
    data is localized

    : Run the benchmark
    : Populate the DB

    input = { product: "",
              specs_vm: {'mapper': ['']),
                      'reducer': ['']}

'''


@app.route('/init', methods=['POST'])
def sla_init():
    data = request.get_json(force=True)
    product_list = data['product_list']
    specs_vm = _format_specs(data['specs_vm'])
    global s3_credentials
    s3_credentials = data['result']['s3_credentials']
    offer = "CannedOffer_1"
    logger.info("Instance sizes: " + str(specs_vm))

    try:
        _check_BDB_state()
        data_loc = find_data_loc(product_list)
        user_clouds = str(get_user_connectors(ss_username))
        data_loc = [c for c in data_loc if c in user_clouds]
        if not data_loc:
            raise ValueError("The data has not been found in any connector \
                             associated with the Nuvla account")
        logger.info("Data located in: %s" % data_loc)
        deployments = run_benchmarks(data_loc, specs_vm, product_list, offer)
        msg = "Cloud %s are currently being benchmarked with %s" % \
              (', '.join(data_loc), ', '.join(deployments))
        status = "201"
    except ValueError as err:
        msg = "Value error: {0} ".format(err)
        status = "404"
        logger.info("Value error: {0} ".format(err))

    resp = Response(msg, status=status, mimetype='application/json')
    return resp


@app.route('/run', methods=['POST'])
def sla_cli():
    index = 'sar'

    try:
        _check_BDB_index(index)
        data = request.get_json()
        _schema_validation(data)
        sla = data['SLA']
        global s3_credentials
        s3_credentials = data['result']['s3_credentials']

        logger.info("SLA: %s" % sla)
        product_list = sla['product_list']
        time = sla['requirements'][0]
        offer = sla['requirements'][1]
        data_loc = find_data_loc(product_list)
        logger.info("Data located in: %s" % data_loc)
        data_loc = _check_BDB_cloud(index, data_loc)
        logger.info("Benchmark run located in: %s" % data_loc)
        msg = ""
        status = ""

        ranking = dmm.dmm(data_loc, time, offer)

        if data_loc and ranking:
            msg = "SLA accepted! "
            status = "201"
            winner = ranking[0]

            logger.info("ranking: %s" % ranking[0:3])
            serviceOffers = {'mapper': winner[1],
                             'reducer': winner[2]}
            deploy_run(winner[0],
                       product_list,
                       serviceOffers,
                       offer,
                       time)  # offer

        else:
            msg = "Data not found in clouds!\n"
            status = 412
    except ValueError as err:
        msg = "Value error: {0} ".format(err)
        status = "404"
        logger.info("Value error: {0} ".format(err))

    resp = Response(msg, status=status, mimetype='application/json')
    return resp


def get_conf_parser(fn):
    global config_parser
    if config_parser is None:
        config_parser = SafeConfigParser()
        config_parser.optionxform = str
        config_parser.read(fn)
    return config_parser


def config_get(opt, default=''):
    parser = get_conf_parser(CONFIG_FILE)
    return parser.get('default', opt, default)


if __name__ == '__main__':
    ss_username = config_get('ss_username')
    ss_password = config_get('ss_password')
    api.login_internal(ss_username, ss_password)
    app.run(host="127.0.0.1", port=int("8080"))
