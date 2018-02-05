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

# {"host": "sos.exo.io",
#  "bucket": "eodata_output",
#  "key": "xxx",
#  "secret": "yyy"}
result_s3_creds = {}

app = Flask(__name__, static_url_path='')
ss_api = Api()
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
    access_key = result_s3_creds.get('key')
    secret_key = result_s3_creds.get('secret')
    host = result_s3_creds.get('host')

    return boto.connect_s3(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        host=host,
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
    logger.info("Downloading product %s." % output_id)
    conn = connect_s3()
    bucket = conn.get_bucket(bucket_id)
    key = bucket.get_key(output_id)
    output_path = os.getcwd() + output_id
    key.get_contents_to_filename(output_path)
    logger.info("Downloaded product %s." % output_id)


def cancel_deployment(deployment_id):
    ss_api.terminate(deployment_id)
    state = ss_api.get_deployment(deployment_id)[2]
    while state != 'cancelled':
        logger.info("Terminating deployment %s." % deployment_id)
        time.sleep(5)
        ss_api.terminate(deployment_id)


def watch_execution_time(start_time):
    time_format = '%Y-%m-%d %H:%M:%S.%f UTC'
    delta = datetime.utcnow() - datetime.strptime(start_time, time_format)
    return delta.seconds


def wait_product(duid, cloud, offer, time_limit):
    dpl_data = ss_api.get_deployment(duid)
    output_id = ""
    states_final = ['ready', 'done']

    while dpl_data.status not in states_final and not output_id:
        dpl_data = ss_api.get_deployment(duid)
        t = watch_execution_time(dpl_data.started_at)
        logger.info("Deployment %s. Waiting state '%s' of '%s'. Time elapsed: %s. SLA time left: %s" %
                    (duid, states_final, str(dpl_data), t, int(time_limit) - int(t)))
        if (t >= time_limit) or dpl_data.status in ["cancelled", "aborted"]:
            cancel_deployment(duid)
            msg = "Deployment %s. SLA time bound %s sec exceeded. Deployment is cancelled." % \
                  (duid, time_limit)
            logger.warn(msg)
            return msg

        time.sleep(45)
        output_id = dpl_data.service_url.split('/')[-1]

    # FIXME: instead of downloading just check that it's there.
    download_product(result_s3_creds.get('bucket'), output_id)
    summarizer.summarize_run(duid, cloud, offer)

    msg = "Deployment %s. Product %s delivered!" % (duid, output_id)
    logger.info(msg)
    return msg


def _all_products_on_cloud(cloud, data_so, prod_list):
    products_cloud = ['xXX' for so in data_so if so['connector']['href'] == cloud]
    return len(products_cloud) >= len(prod_list)


def _to_list(data):
    if isinstance(data, unicode) or isinstance(data, str):
        data = [data]
    return data


def find_data_loc(api, prod_list):
    resp = sc.request_data(api, prod_list)
    data_so = resp['serviceOffers']
    clouds_s3 = {}
    # Current deployment algorithm doesn't support clouds
    # that store data in multiple buckets.
    clouds_black_listed = []
    for so in data_so:
        cloud = so['connector']['href']
        s3host = so['resource:host']
        s3bucket = so['resource:bucket']
        if cloud not in clouds_s3 and cloud not in clouds_black_listed:
            clouds_s3[cloud] = {'s3host': s3host, 's3bucket': s3bucket}
        else:
            if s3host == clouds_s3[cloud]['s3host'] and \
                    s3bucket == clouds_s3[cloud]['s3bucket']:
                pass
            else:
                del clouds_s3[cloud]
                clouds_black_listed.append(cloud)
                logger.info('Blacklisted cloud for storing products in '
                            'multiple buckets: %s' % cloud)
    clouds_s3_legit = {}
    for cloud in clouds_s3:
        if _all_products_on_cloud(cloud, data_so, prod_list):
            clouds_s3_legit[cloud] = clouds_s3[cloud]
    logger.info('Products are on clouds: %s', clouds_s3_legit)
    return clouds_s3_legit


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


def run_benchmarks(clouds_s3, specs_vm, product_list, offer):
    index = 'sar'
    req_index = requests.get(elastic_host + '/' + index)
    if not req_index:
        populate_db(index)

    deployments = []
    for cloud, s3 in clouds_s3.iteritems():
        populate_db(index, cloud)
        vm_service_offers = _vm_service_offers(cloud, specs_vm)
        deployment_id = deploy_run(cloud, s3, product_list, vm_service_offers, offer, 9999)
        logger.info("Deployed run: %s on cloud %s with VM service offers %s and data in %s" %
                    (deployment_id, cloud, str(vm_service_offers), s3))
        deployments.append(deployment_id)
    return deployments


def _check_BDB_cloud(index, clouds):
    valid_cloud = []
    for c in _to_list(clouds):
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


def _get_vm_so(specs, clouds, name):
    resp = sc.request_vm(ss_api, specs, clouds)
    if 'serviceOffers' not in resp:
        raise Exception('Failed to find SOs for %s %s on clouds %s.' % (name, specs, clouds))
    return resp['serviceOffers'][0]['id']


def _get_mapper_so(specs, clouds):
    n = 'mapper'
    return _get_vm_so(specs[n], clouds, n)


def _get_reducer_so(specs, clouds):
    n = 'reducer'
    return _get_vm_so(specs[n], clouds, n)


def _vm_service_offers(cloud, specs):
    clouds = ["connector/href='%s'" % cloud]
    mapper_so = _get_mapper_so(specs, clouds)
    reducer_so = _get_reducer_so(specs, clouds)
    service_offers = {'mapper': mapper_so, 'reducer': reducer_so}
    return service_offers


def deploy_run(cloud, s3, product, vm_service_offers, offer, timeout):
    server_ip = config_get('dmm_ip')
    server_hostname = config_get('dmm_hostname')
    mapper_so = vm_service_offers['mapper']
    reducer_so = vm_service_offers['reducer']

    if mapper_so and reducer_so:
        mapper_params = {'service-offer': mapper_so,
                         'product-list': ' '.join(product),
                         's3-host': s3['s3host'],
                         's3-bucket': s3['s3bucket'],
                         'server_hn': server_hostname,
                         'server_ip': server_ip}
        # FIXME: need to provide user's S3 endpoint, bucket and creds for results.
        reducer_params = {'service-offer': reducer_so,
                          'server_hn': server_hostname,
                          'server_ip': server_ip}
        comps_params = {'mapper': mapper_params,
                        'reducer': reducer_params}
        comps_counts = {'mapper': len(product),
                        'reducer': 1}
        proc_module = config_get('ss_module_proc_sar')
        comps_clouds = {'mapper': cloud, 'reducer': cloud}
        logger.info('Deploying: on "%s" with params "%s" and multiplicity "%s".' %
                    (comps_clouds, comps_params, comps_counts))
        deployment_id = ss_api.deploy(proc_module,
                                      cloud=comps_clouds,
                                      parameters=comps_params,
                                      multiplicity=comps_counts,
                                      tags='EOproc',
                                      keep_running='never')
        daemon_watcher = Thread(target=wait_product, args=(deployment_id, cloud, offer, timeout))
        daemon_watcher.setDaemon(True)
        daemon_watcher.start()
        return '%s/run/%s' % (ss_api.endpoint, deployment_id)
    else:
        msg = "No suitable instance types found for mapper and reducer on cloud %s" % cloud
        logger.warn(msg)
        return msg


def get_user_connectors(user):
    cloud_set = ss_api.get_user(user).configured_clouds
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
            logger.info('SLA cost found item: %s' % item)
            item = item['_source']
            for k, v in item.items():
                specs = _format_specs(v['components'])
                ids = _vm_service_offers(c, specs)
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
    global result_s3_creds
    result_s3_creds = data['result']['s3_credentials']
    offer = "CannedOffer_1"
    logger.info("Instance sizes: " + str(specs_vm))

    try:
        _check_BDB_state()
        clouds_s3 = find_data_loc(ss_api, product_list)
        user_clouds = str(get_user_connectors(ss_username))
        if not [c for c in clouds_s3 if c in user_clouds]:
            raise ValueError("The data has not been found in any connector \
                             associated with the Nuvla account %s" % ss_username)
        logger.info("Data located in: %s" % clouds_s3)
        deployments = run_benchmarks(clouds_s3, specs_vm, product_list, offer)
        msg = "Cloud %s are currently being benchmarked with %s" % \
              (', '.join(clouds_s3.keys()), ', '.join(deployments))
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

        global result_s3_creds
        result_s3_creds = data['result']['s3_credentials']

        sla = data['SLA']
        logger.info("SLA: %s" % sla)
        product_list = sla['product_list']
        time = sla['requirements'][0]
        offer = sla['requirements'][1]
        data_loc = find_data_loc(ss_api, product_list)
        logger.info("Data located in: %s" % data_loc)
        data_loc = _check_BDB_cloud(index, data_loc)
        logger.info("Benchmark run located in: %s" % data_loc)
        msg = ""
        status = ""

        cloud_ranking = dmm.dmm(data_loc, time, offer)

        if data_loc and cloud_ranking:
            msg = "SLA accepted! "
            status = "201"
            cloud_winner = cloud_ranking[0]

            logger.info("cloud ranking: %s" % cloud_ranking[0:3])
            serviceOffers = {'mapper': cloud_winner[1],
                             'reducer': cloud_winner[2]}
            deploy_run(cloud_winner[0],
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
    ss_api.login_internal(ss_username, ss_password)
    app.run(host="127.0.0.1", port=int("8080"))
