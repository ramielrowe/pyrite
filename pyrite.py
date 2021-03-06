import io
import logging
import os

import flask
import requests
import yaml


def load_config(path):
    with open(path, 'r') as fp:
        return yaml.load(fp)

GRAPHITE_ADDR_VAR = 'GRAPHITE_PORT_80_TCP_ADDR'
GRAPHITE_PORT_VAR = 'GRAPHITE_PORT_80_TCP_PORT'

GRAPHITE_ADDR = os.environ.get(GRAPHITE_ADDR_VAR, 'localhost')
GRAPHITE_PORT = os.environ.get(GRAPHITE_PORT_VAR, '50080')

GRAPHITE_SERVER_BASE = os.getenv('GRAPHITE_SERVER_BASE',
                                 'http://%s:%s/render/' % (GRAPHITE_ADDR,
                                                           GRAPHITE_PORT))

CONFIG_PATH = os.getenv('PYRITE_CONFIG_PATH', './pyrite.yaml')
CONFIG = load_config(CONFIG_PATH)
APP = flask.Flask(__name__)

@APP.before_first_request
def setup_logging():
    if not APP.debug:
        APP.logger.addHandler(logging.StreamHandler())
        APP.logger.setLevel(logging.DEBUG)


def add(url_params, conf, url_key, conf_key=None, default=None):
    url_params[url_key] = conf.get(conf_key or url_key, default)


def add_color(url_params, conf, color_index, url_key, conf_key=None):
    url_params[url_key] = conf[conf_key or url_key][color_index]


def add_if_present(url_params, conf, url_key, conf_key=None):
    conf_key = conf_key or url_key
    if conf_key in conf:
        url_params[url_key] = conf[conf_key or url_key]


def add_targets(url_params, conf):
    colors = []
    for i in range(1, len(conf['data']) + 1):
        alias = conf['data'][i].keys()[0]
        datum = conf['data'][i][alias]

        target = datum['target']

        if isinstance(target, list):
            target = ','.join(target)
            target_func = datum['target_func']
            funcs = []

            if isinstance(target_func, basestring):
                funcs.append(target_func)

            for func in funcs:
                target = '{}({})'.format(func, target)

        keep_last_value = datum.get('keep_last_value')
        if keep_last_value:
            target = 'keepLastValue({},{})'.format(target, keep_last_value)

        if not datum.get('no_alias'):
            target = 'alias({},"{}")'.format(target, alias.replace('_', ' '))
        url_params['target'].append(target)

        if 'color' in datum:
            colors.append(datum['color'])
    return colors


def build_graph_url_params(name, color_index):
    conf = CONFIG['graphs'][name]
    url_params = dict(target=list())
    url_params['title'] = name.replace('_', ' ')
    add(url_params, conf, 'width')
    add(url_params, conf, 'height')
    add_color(url_params, conf, color_index, 'bgcolor')
    add_color(url_params, conf, color_index, 'fgcolor')
    add_color(url_params, conf, color_index, 'majorGridLineColor')
    add_color(url_params, conf, color_index, 'minorGridLineColor')
    add(url_params, conf, 'lineWidth', default=1)
    add_if_present(url_params, conf, 'yMin')
    add_if_present(url_params, conf, 'yMax')
    add_if_present(url_params, conf, 'yStep')
    add_if_present(url_params, conf, 'areaMode')
    colors = add_targets(url_params, conf)
    url_params['colorList'] = ','.join([color[color_index] for color in colors])
    return url_params


@APP.route("/graph/<name>")
def graph(name):
    if name not in CONFIG['graphs']:
        flask.abort(404)

    request = flask.request
    color_index = int(request.args.get('color_index', 0))
    _from = request.args.get('from', '-6hours')

    url_params = build_graph_url_params(name, color_index)
    url_params['from'] = _from
    resp = requests.get(GRAPHITE_SERVER_BASE, params=url_params)
    return flask.send_file(io.BytesIO(resp.content),
                           mimetype='image/png',
                           attachment_filename='{}.png'.format(name),
                           cache_timeout=0)


PAGE_HTML = """
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
  <head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <title>Home</title>
    <style type="text/css">
      body {
        background-color: %(bgcolor)s;
      }
      div.header {
        width: 800px;
        margin-left: auto;
        margin-right: auto;
        text-align: center;
      }
      div.row {
        max-width: 1800px;
        width: 95%%;
        margin-left: auto;
        margin-right: auto;
        text-align: center;
      }
    </style>
  </head>
  <body>
  <div class="header">
  %(links)s
  </div>
  %(rows)s
  </body>
</html>"""

ROW_HTML = """
  <div class="row">
%(images)s
  </div>"""

IMAGE_HTML = '    <img src="/graph/%(image_name)s?from=%(from)s&color_index=%(color_index)s" />'

LINK_HTML = '    <a href="/%(page)s?%(args)s">%(name)s</a>'
LINK_SEP = ' - '


def make_page(name):
    page_config = CONFIG['pages'][name]
    default_color_index = page_config.get('default_color_index', 0)
    default_from = page_config.get('default_from', '-6hours')

    request = flask.request
    context = dict()
    context['color_index'] = int(request.args.get('color_index',
                                                  default_color_index))
    context['from'] = request.args.get('from', default_from)

    links = list()
    for i in range(1, len(page_config['links']) + 1):
        link_config = page_config['links'][i]
        args = list()
        for key, value in link_config['args'].iteritems():
            args.append('%s=%s' % (key, value))
        links.append(LINK_HTML % dict(name=link_config['name'],
                                      page=link_config['page'],
                                      args='&'.join(args)))
    links_html = LINK_SEP.join(links)

    rows = list()
    for i in range(1, len(page_config['rows']) + 1):
        row_config = page_config['rows'][i]
        images = list()
        for j in range(1, len(row_config) + 1):
            img_name = row_config[j]
            image_dict = dict(image_name=img_name)
            image_dict.update(context)
            images.append(IMAGE_HTML % image_dict)
        images_html = '\n'.join(images)
        rows.append(ROW_HTML % dict(images=images_html))

    rows_html = ''.join(rows)
    page_dict = dict(links=links_html,
                     rows=rows_html,
                     bgcolor=page_config['bgcolor'][context['color_index']])
    page_dict.update(context)
    return PAGE_HTML % page_dict

@APP.route("/")
def index():
    return make_page('index')

@APP.route("/<name>")
def page(name):
    if name not in CONFIG['pages']:
        flask.abort(404)

    return make_page(name)


if __name__ == '__main__':
    APP.run(host='0.0.0.0', debug=True)
