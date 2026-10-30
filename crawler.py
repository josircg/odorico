import os
import random
import time
import requests
from django.http import Http404

from odorico import settings

from lxml.html import fromstring
from bs4 import BeautifulSoup

PROXY_LIST = [None, ]
USER_AGENT_CHOICES = [
    'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:23.0) Gecko/20100101 Firefox/23.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/29.0.1547.62 Safari/537.36',
    'Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.2; WOW64; Trident/6.0)',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/33.0.1750.146 Safari/537.36',
    'Mozilla/5.0 (Windows NT 6.2; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/33.0.1750.146 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64; rv:24.0) Gecko/20140205 Firefox/24.0 Iceweasel/24.3.0',
    'Mozilla/5.0 (Windows NT 6.2; WOW64; rv:28.0) Gecko/20100101 Firefox/28.0',
    'Mozilla/5.0 (Windows NT 6.2; WOW64; rv:28.0) AppleWebKit/534.57.2 (KHTML, like Gecko) Version/5.1.7 Safari/534.57.2',
]


def get_cache(identifier):
    filename = os.path.join(settings.BASE_DIR, 'cache', '%s.html' % identifier)
    if not os.path.isfile(filename):
        return None
    else:
        with open(filename, 'r') as file:
            texto = file.read()
        last_soap = BeautifulSoup(texto, 'html.parser')
        return last_soap


def save_cache(identifier, soap):
    basedir = os.path.join(settings.BASE_DIR, 'cache')
    filename = os.path.join(basedir, '%s.html' % identifier)
    if not os.path.isdir(basedir):
        os.mkdir(basedir)
    with open(filename, 'w') as file:
        file.write(str(soap))


def get_proxies():
    url = 'https://free-proxy-list.net/'
    headers = {'user-agent': random.choice(USER_AGENT_CHOICES)}
    response = requests.get(url, headers=headers)
    parser = fromstring(response.text)
    lista = []
    for i in parser.xpath('//tbody/tr')[:10]:
        if i.xpath('.//td[7][contains(text(),"yes")]'):
            proxy = ":".join([i.xpath('.//td[1]/text()')[0], i.xpath('.//td[2]/text()')[0]])
            lista.append(proxy)
    print('Proxies obtidos: %d' % len(lista))
    return lista


def get_page(url, fast=False, timeout=10):
    global PROXY_LIST
    last_soup = 404
    headers = {'user-agent': random.choice(USER_AGENT_CHOICES)}
    while len(PROXY_LIST) > 0:
        if fast:
            proxy = ''
        else:
            proxy = random.choice(PROXY_LIST)
        try:

            if proxy:
                response = requests.get(url, headers=headers, proxies={"http": proxy, "https": proxy, }, timeout=30)
            else:
                response = requests.get(url, headers=headers, timeout=timeout)

            if response.status_code == 200:
                # print('%s proxy(%s)' % (url, proxy))
                last_soup = BeautifulSoup(response.text, 'html.parser')
                break
            elif fast or response.status_code == 403:
                raise Http404
            else:
                raise Exception('Blocked')
        except Exception as e:
            if proxy != '':
                PROXY_LIST.remove(proxy)
                print('Dead Proxy: %s - Left: %d' % (proxy, len(PROXY_LIST)))
                while len(PROXY_LIST) == 0:
                    time.sleep(60)
                    PROXY_LIST = get_proxies()
            else:
                raise

    return last_soup
