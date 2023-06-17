# -*- coding: utf-8 -*-

from collections import Counter

def remove_charlist(text, charlist, sep):
    """
    Args:
        text (str): Texto
        charlist (list): Lista com strings a serem removidas.
        sep (char): new separator
    Returns:
        str
    """
    result = ''
    for c in text:
        result += sep if c in charlist else c

    return result


# Cria uma lista com as frases criadas a partir dos delimitadores informados
def make_phrases(texto, separators):
    return [x for x in remove_charlist(texto, separators, '.').split('.') if x]


# Texto: Texto Livre que será quebrado em palavras e Bigramas
# Keywords: Lista de Palavras Chaves que tem que entrar sem ser quebradas em palavras
# Stopwords: Lista de Palavras que não devem ser incluídas na tabela final
#
def build_wordcloud(texto, keywords, stopwords=None):

    if stopwords is None:
        stopwords = []

    texto = remove_charlist(texto, ['’', '”', '`', '"', '\t', '\r', '\''], ' ')

    phrase_delimiters = [':', '.', ',', ';', '?', '!', '\n']
    words = make_phrases(texto, phrase_delimiters + [' '])

    phrases_list = make_phrases(texto, phrase_delimiters)
    bigrams = ['%s %s' % (ele, tex.split()[ i + 1 ]) for tex in phrases_list for i, ele in enumerate(tex.split()) if
                i < len(tex.split()) - 1]

    for index, termo in enumerate(bigrams):
        if len(termo.split(' ')[-1]) < 3 and index + 1 < len(bigrams):
            bigrams[index] = ' '.join(bigrams[index].split(' ')[:-1]) + ' ' + bigrams[index + 1]
            del bigrams[index + 1]

    for item in keywords:
        for chave in make_phrases(item, [',', ';', '.']):
            if len(chave.strip()) > 2:
                bigrams.append(chave.strip())

    if len(stopwords) > 0:
        stopwords = set(stopwords)

    cleaned = []
    for word in words:
        if termo.upper() == termo and len(termo) < 8:
            if termo.isdigit():
                termo = ''
        else:
            termo = word.lower()

        if len(termo) > 2 and termo not in stopwords:
            cleaned.append(termo)

    for termo in bigrams:
        if termo.upper() == termo and len(termo) < 8:
            cleaned.append(termo)
        else:
            cleaned.append(termo.lower())

    words_frequency = Computation.frequently(list_words=cleaned)

    return words_frequency


class Computation:
    """
        Classe que manipula estatistica e frequência de palavras numa lista
        de frases e de frequência.
    """
    @staticmethod
    def frequently(list_words, quantity=None, list_ignore=[]):
        """Cria uma lista com as palavras mais frequentes
        Args:
            list_words (list): Lista de frases.
            quantity (int): Quantidades de palavras a serem recuperadas.
            list_ignore (list): Lista de palavras a serem desconsideradas.
        Returns:
            list
        """
        if quantity:
            fq = Counter(list_words).most_common(quantity)
        else:
            fq = Counter(list_words).most_common()

        if list_ignore:
            for lw in list_words:
                if lw[0] in list_ignore:
                    if not fq:
                        fq.append(lw)
                    else:
                        for f in fq:
                            if lw[0] not in f:
                                fq.append(lw)
        return fq

    @staticmethod
    def more_less_frequently(list_words, cut_frequently, list_ignore=[], more=True):
        """Com lista de Counter(de palavras) filtrar as de maiores ou menores frequências.
        Args:
            list_words (list(Counter)): Lista de frases.
            cut_frequently (int): Frequencia de corte.
            list_ignore (list): Lista de palavras a serem desconsideradas.
            more (bool): True - frequencia >= cut_frequently. False - frequência <= cut_frequently.
        Returns:
            list
        """
        more_less = []
        if more:
            more_less = [w[0] for w in list_words if w[1] >= cut_frequently]
        else:
            more_less = [w[0] for w in list_words if w[1] <= cut_frequently]

        for lw in list_words:
            if lw[0] in list_ignore:
                if not more_less:
                    more_less.append(lw[0])
                else:
                    for mf in more_less:
                        if lw[0] not in mf:
                            more_less.append(lw[0])

        return more_less
