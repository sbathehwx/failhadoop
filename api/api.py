#!/usr/local/bin/python3

from __future__ import print_function
import os, sys, json, flask, requests, glob
from collections import defaultdict
import failhadoop
import subprocess
import logging
import logging.handlers

#TODO:  /random is right now hardcoded. Make it configurable / generic

# The config file for the API. It will contain a default cluster definition and
# specification as well. Would be similar to the failhadoop config file
# Minimum required:
#    1 - Failhadoop config root
#    2 - Testcase Root

# Log file for the web component
SYSTEM_LOG_FILENAME = 'api.log'

#lockfile to write. has a format
# <Cluster>:<component>:<number>:<start time>
lockfile = 'api.lock'
cfg_file = 'api.json'

with open(cfg_file) as f:
  flask_conf = json.load(f)

base_uri = '/failhadoop'
app = flask.Flask(__name__)

def run_test(flask_conf, cluster_config=flask_conf['failhadoop_default_config'],
             cluster=flask_conf['failhadoop_default_cluster'], component='random', testnumber=None):
    conf_root = flask_conf['failhadoop_config_root']
    full_path = os.path.join(conf_root, cluster_config + '.json')
    if not os.path.exists(full_path):
        return "Required config file {0} in the URL is not on this server".format(full_path), 500
    msg = dict()
    data = failhadoop.web_utils.read_lock(lockfile)
    app.logger.debug('Checking if cluster: {0} is in use. Data in file is {1}'.format(cluster,data))
    lock = failhadoop.web_utils.check_lock(data,cluster)
    app.logger.debug('{0}'.format(lock))
    cmd = ['fail.py',
           '-c','{0}/{1}.json'.format(conf_root,cluster_config),'-i','{0}/inventory/'.format(conf_root),'--testcase-root',
           '{0}'.format(flask_conf['testcase_root']),'-v']
    if component == 'random':
        cmd.append('--random')
    if flask_conf['dry-run']:
        cmd.append('--dry-run')
    if lock:
        msg[0] = 'Cannot run test. Cluster {0} is already in use\n\t\t{1}'.format(cluster,failhadoop.web_utils.get_lock_data(data,cluster))
    else:
        if failhadoop.web_utils.write_new_lock(lockfile, cluster, component, testnumber):
          p = subprocess.Popen(cmd,stdout =
                           subprocess.PIPE,stderr=subprocess.PIPE,stdin=subprocess.PIPE)
          msg[0], msg[1] = p.communicate()
        else:
           msg[0] = 'Failed to write lock for the test'
    return msg

@app.route(base_uri, methods = ['GET'])
def return_help():
    help_text = '''
    You have reached root of failures.</br>
    /failhadoop/configs will tell you about the configs I hold</br>
    /failhadoop/random will run a random failure on the default cluster</br>
    /failhadoop/{config}/{cluster}/random will run a random failure on the
    specific cluster</br>
    /failhadoop/{config}/{cluster}/{service}/{testnumber} will run the
    specified test on the specified config and cluster</br>
    '''
    return help_text, 200

@app.route(base_uri + '/configs', methods = ['GET'])
def return_configs_and_clusters():
    service_dict = failhadoop.utils.return_testcase_dict(flask_conf['testcase_root'])
    confs = glob.glob(flask_conf['failhadoop_config_root']+'/*.json')
    app.logger.debug('Confs: {0}'.format(confs))
    conf_dict = defaultdict(list)
    for c in confs:
        ac = failhadoop.ambari_helpers.load_config(c)
        ambari_session = failhadoop.ambari_helpers.setup_ambari_session(ac)
        clusters = failhadoop.ambari_helpers.get_clusters(ac, ambari_session)
        conf_dict[c].append(clusters)
    print('conf_dict: {0}'.format(conf_dict))
    return flask.render_template('show_configs.html', conf_dict=conf_dict,
                                 service_dict=service_dict)

@app.route(base_uri + '/random', methods = ['GET'])
def run_random_failure():
    msg = run_test(flask_conf)
    return flask.jsonify(msg)

@app.route(base_uri + '/<config>/<cluster>/random', methods = ['GET'])
def run_random_failure_on_cluster(config, cluster):
    msg = run_test(flask_conf, config, cluster) 
    return flask.jsonify(msg)

@app.route(base_uri + '/<config>/<cluster>/<service>/<testnumber>', methods = ['GET'])
def run_failure_on_cluster(config, cluster, service, testnumber):
    msg = run_test(flask_conf, config, cluster, service, testnumber)
    return flask.jsonify(msg)

if __name__ == '__main__':
    debug = True
    app.logger.setLevel(logging.DEBUG)  # use the native logger of flask
    app.logger.disabled = False
    handler = logging.handlers.RotatingFileHandler(
        SYSTEM_LOG_FILENAME, 'a',
        maxBytes=1024 * 1024 * 100,
        backupCount=20
        )
    formatter = logging.Formatter(\
        "%(asctime)s - %(levelname)s - %(name)s: \t%(message)s")
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)

    log = logging.getLogger('werkzeug')
    log.setLevel(logging.DEBUG)
    log.addHandler(handler)

    if flask_conf['dry-run']:
      app.logger.info('Running in Dry Run mode')
    else:
      app.logger.info('Running Live mode')
    app.run(host='0.0.0.0', debug=debug)
