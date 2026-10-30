import os, sys, shutil, re
import logging
import csv
import hashlib
from odorico import settings
from datetime import datetime, timedelta

from bs4 import NavigableString
from stdnum import issn
from crawler import get_cache, get_page, save_cache

import io
import requests
from zipfile import ZipFile, BadZipFile

# Obtem o XML do Lattes via VPN
def get_lattes_xml(id_cnpq):
    response = requests.get(f'http://172.16.16.195:5000/curriculo/{id_cnpq}', timeout=15)
    if response.status_code == 200:
        pathname = os.path.join(settings.BASE_DIR, 'data')
        z = ZipFile(io.BytesIO(response.content))
        print(pathname)
        z.extractall(pathname)
        # with open(pathname + '/' + id_cnpq + '.xml', 'rb') as arquivo_xml:
        #   xml = arquivo_xml.read().decode('ISO-8859-1')


def tipo_apresentacao(div):
    texto = div.text
    if 'Ouvinte' in texto:
        return 'Ouvinte'
    if 'Participante' in texto:
        return 'Participante'


def leitura_pesquisadores(arquivo):
    if os.path.isfile(arquivo):
        lista = []
        with open(arquivo, 'r') as csvfile:
            fieldnames = ['id', 'nome', 'status']
            reader = csv.DictReader(csvfile, fieldnames)
            for row in reader:
                lista.append(row)
        return lista
    else:
        return None


def get_dtupdate(soup):
    marker = soup.find('span', attrs={'class': 'img_cert'})
    if marker:
        texto = marker.next.split()
        try:
            return datetime.strptime(texto[-1], '%d/%m/%Y')
        except:
            None
    return None


def get_id_cnpq(soup):
    marker = soup.find('span', attrs={'class': 'img_link'})
    if marker:
        texto = marker.next.split('http://lattes.cnpq.br/')
        return texto[1].strip()
    else:
        return None


def find_pais(texto, paises):
    final = None
    if 'Referências adicionais' in texto:
        final = texto.split('Referências adicionais')[1]
        final = final.split('/')[0]
        final = re.sub("[.;:]", '', final)
        final = final.strip()
    if 'Classificação do evento: Internacional' in texto:
        final = texto.split('Classificação do evento: Internacional')[1]
        final = final.split('/')[0]
        final = re.sub("[.;:]", '', final)
        final = final.strip()
    if final:
        final = final.replace('Tipo de participação', '')
        final = final.replace('Classificação do evento', '')
        final = final.replace('Conferencista', '')
        final = final.replace('http', '')
        final = final.replace('Homepage', '')
        final = final.replace('Simposiasta', '')
        final = final.replace('Speaker', '')
        final = final.replace('Moderador', '')
        final = final.replace('Convidado', '')
        final = final.replace('Avaliador', '')
        final = final.replace('Forma de participação', '')
        final = final.strip()
        resultado = list(filter(lambda pais: pais['nome'] == final, paises))
        if resultado:
            return resultado[0]['iso3']
        else:
            texto = final.split()[0]
            resultado = list(filter(lambda pais: pais['nome'] == texto, paises))
            if resultado:
                return resultado[0]['iso3']
            else:
                texto = final.split()[-1]
                resultado = list(filter(lambda pais: pais['nome'] == texto, paises))
                if resultado:
                    return resultado[0]['iso3']
            print('*%s*' % final)
    return None


def get_producao(soup):
    producao = []
    # Primeiro processamento: Artigos Completos
    artigos = soup.find('div', attrs={'id': 'artigos-completos'})
    if artigos:
        artigos = artigos.find_all('div','artigo-completo')
    else:
        artigos = []
    for artigo in artigos:
        marker = artigo.find_next('div')
        while marker:
            if 'layout-cell-pad-5' in marker.attrs['class'] and len(marker.attrs['class']) == 1:
                texto = ''
                doi = ''
                keywords = ''
                for elemento in marker.children:
                    result = ''
                    if isinstance(elemento, NavigableString):
                        if elemento.strip():
                            result = elemento
                    else:
                        if elemento.has_attr('class') and 'icone-doi' in elemento.attrs['class']:
                            doi = elemento['href']
                        if not elemento.has_attr('data-tipo-ordenacao'):
                            if elemento.text.strip():
                                result = elemento.text

                    if result.startswith('Palavras-chave'):
                        keywords = result.replace('Palavras-chave:', '').strip(' .')
                    elif not result.startswith('Meio de divulgação:'):
                        texto += result
                producao.append({'type': 'artigo', 'text': texto, 'keywords': keywords, 'doi': doi})
                marker = None
            else:
                marker = marker.find_next('div')

    count = 0
    for maindiv in soup.find_all("div", attrs={'class': 'title-wrapper'}):
        titulo = maindiv.find('a')

        if titulo and 'name' in titulo.attrs and titulo.attrs['name'] == 'ProducoesCientificas':

            marker = maindiv.find('div',attrs={'id': 'artigos-completos'})
            if marker:
                marker = marker.find_next('div', attrs={'class': 'cita-artigos'})
                marker = marker.find_next('div', attrs={'class': 'cita-artigos'})
            else:
                marker = maindiv.find('div', attrs={'class': 'cita-artigos'})

            while marker:
                titulo = marker.find('a')
                if not titulo:
                    break

                tipo = titulo.attrs['name']
                # print('\n***%s***' % marker.find('b').text)
                marker = marker.find_next('div')
                while marker and 'cita-artigos' not in marker.attrs['class']:
                    if 'layout-cell-pad-5' in marker.attrs['class'] and len(marker.attrs['class']) == 1:
                        if marker.text:
                            publicacao = " ".join(marker.text.split())
                            producao.append({'type': tipo, 'text': publicacao, 'keywords': ''})
                    marker = marker.find_next('div')
                    if marker and 'title-wrapper' in marker.attrs['class']:
                        marker = None

        if titulo and 'name' in titulo.attrs and \
                titulo.attrs['name'] in ['Eventos', 'ParticipacaoBancasTrabalho', 'ParticipacaoEventos',
                                         'OrganizacaoEventos']:
            tipo = titulo.attrs['name']
            for div in maindiv.find_all('div','layout-cell-pad-5'):
                if len(div.attrs['class']) == 1:
                    if tipo_apresentacao(div) not in ['Participante', 'Ouvinte']:
                        if div.text:
                            publicacao = " ".join(div.text.split())
                            producao.append({'type': tipo, 'text': publicacao, 'keywords': ''})
    return producao


def read_lattes(id, nome):
    soup = get_cache(id)
    if not soup:
        try:
            soup = get_page('http://buscatextual.cnpq.br/buscatextual/visualizacv.do?metodo=apresentar&id=%s&tipo=completo&idiomaExibicao=1' % id)
            if soup:
                save_cache(id, soup)
        except:
            soup = None

    pesquisador = {'id': id}
    if soup:
        pesquisador['nome'] = soup.find('h2', attrs={'class': "nome"}).text
        if nome and pesquisador['nome'].upper() != nome.upper():
            print('Nome diferente da base Lattes')
        pesquisador['status'] = 'A'
        pesquisador['dtupdate'] = get_dtupdate(soup)
        pesquisador['id_cnpq'] = get_id_cnpq(soup)
    else:
        pesquisador['status'] = 'E'
        print('ID não encontrado: %s' % id)
        return

    pesquisador['producao'] = get_producao(soup)
    return pesquisador


def get_parse_issn(titulo):
    try:
        if 'ISSN/ISBN' in titulo:
            result = titulo.split('ISSN/ISBN')[1]
            result = ''.join(c for c in result if c not in '"(){}<>:,.').strip().split(' ')[0]
            result = issn.format(result)
            issn.validate(result)
            return result
    except:
        return None


def parse_periodico(titulo):
    # encontra o primeiro autor considerando que o título está utilizando a ABNT. Exemplo:
    #
    # PECI, A. ; FORNAZIN, M. . The knowledge-building process of public administration research: a comparative
    # perspective between Brazil and North American contexts. INTERNATIONAL REVIEW OF ADMINISTRATIVE SCIENCES,
    # v. 83, p. 99-119, rint; Meio de divulgação: Digital. Homepage: ; Série: 1;
    #
    # busca pelo ". ." que identifica o início do título.
    # Busca-se de trás para frente
    result = titulo.split('. .')[1]
    result = result.split('v.')[0].split('.')[-1].strip().strip(',')
    return result


def dedup_key(issn, titulo):
    # Monta um hash que identifica o título para otimizar a deduplicação
    if issn:
        result = hashlib.md5((issn+titulo).encode()).hexdigest()
    else:
        result = hashlib.md5(('0000-0000'+titulo).encode()).hexdigest()

    return result


def get_lista_paises():
    result = []
    with open(os.path.join(settings.BASE_DIR, 'data/paises.csv'), mode='r') as read_file:
        csv_reader = csv.DictReader(read_file, skipinitialspace=True)
        for row in csv_reader:
            result.append(row)
    return result


# "Prafrentemente não vai melhorar!"
# Odorico Paraguaçu

# Mapas
# http://www.pygal.org/en/stable/documentation/output.html#django-response

if __name__ == "__main__":
    logger = logging.getLogger(__name__)
    logging.basicConfig(format='%(asctime)s - %(levelname)s (%(name)s) - %(message)s')
    logging.root.setLevel(level=logging.ERROR)
    logger.info("Executando '{}'".format(' '.join(sys.argv)))

    PROXY_LIST = [ None, ]
    ANO = '2018'

    #PROXY_LIST = get_proxies()
    #if len(PROXY_LIST) == 0:
    #    raise Exception('No proxies found')

    lista = leitura_pesquisadores(sys.argv[1])
    if not lista:
        print('Arquivo com a lista de pesquisadores não encontrado: %s' % sys.argv[1])
        exit(-1)

    shutil.copy('header.html', 'output.html')
    output = open('output.html', 'a')

    producao = open('producao.csv','w')
    writer = csv.writer(producao, delimiter=',', quotechar='"')
    writer.writerow(['idlattes','id','tipo','texto','keywords','doi'])

    tot_registros = 0
    tot_erro = 0
    pesquisadores = []
    sem_producao = []
    for chave in lista:
        if chave['id']:
            pesquisador = read_lattes(chave['id'],chave['nome'])
            pesquisadores.append(pesquisador)
            cnt = 0
            if pesquisador['status'] == 'E':
                tot_erro += 1
            else:
                secao = '#'
                producao_html = ''
                for item in pesquisador['producao']:
                    writer.writerow([pesquisador['id'],
                                     cnt,
                                     item['type'],
                                     item['text'],
                                     item.get('keywords',''),
                                     item.get('doi','')])
                    if ANO in item['text']:
                        if secao != item['type']:
                            secao = item['type']
                            producao_html += '<p><b>%s</b></p>' % secao
                        producao_html += '<p>%s</p>' % item['text']
                        cnt += 1

                if cnt > 0:
                    if 'dtupdate' in pesquisador:
                        dtupdate = pesquisador['dtupdate'].strftime('%d/%m/%Y')
                        if pesquisador['dtupdate'] < datetime.today() - timedelta(days=60):
                            dtupdate = '<p>Dt.Atualização:<span style="color:red;">%s</span></p>' % dtupdate
                        else:
                            dtupdate = '<p>Dt.Atualização:%s</p>' % dtupdate

                    output.write(
                        '<br>\n<h2><a target="_blank" rel="noopener noreferrer" href="http://buscatextual.cnpq.br/buscatextual/visualizacv.do?metodo=apresentar&id=%s&tipo=completo&idiomaExibicao=1">%s</a></h2>%s' %
                        ( pesquisador['id'],
                          pesquisador['nome'],
                          dtupdate))
                    output.write(producao_html)
                else:
                    sem_producao.append(pesquisador)
            tot_registros += cnt

    output.write('<br/><b>Total de Pesquisadores: %d</b>' % len(pesquisadores))
    output.write('<br/><b>Pesquisadores sem produção em %s: %d</b>' % (ANO, len(sem_producao)))
    output.write('<br/>')
    for sujeito in sem_producao:
        output.write(
            '<br>\n<a target="_blank" rel="noopener noreferrer" href="http://buscatextual.cnpq.br/buscatextual/visualizacv.do?metodo=apresentar&id=%s&tipo=completo&idiomaExibicao=1">%s</a>' % (
            sujeito['id'], sujeito['nome']))
    output.write('</body></html>')
    output.close()
    producao.close()
    print('Processamento concluído')
    print('Total de Pesquisadores: %d' % len(pesquisadores))
    print('Total de Pesquisadores com erro: %d' % tot_erro)
    print('Total de Entradas em 2018: %d' % tot_registros)
