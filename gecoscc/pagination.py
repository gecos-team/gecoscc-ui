# -*- coding: utf-8 -*-

#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Pablo Martin <goinnn@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import paginate as paginate
from webhelpers2.html import HTML, literal
import logging

logger = logging.getLogger(__name__)

class BootStrapPage(paginate.Page):

    def pager(self, format='$link_previous ~2~ $link_next', url=None,
        show_if_single_page=False, separator=' ', symbol_first='&lt;&lt;',
        symbol_last='&gt;&gt;', symbol_previous=u'«', symbol_next=u'»',
        link_attr=dict(), curpage_attr=dict(), dotdot_attr=dict(),
        link_tag=None):
         
        link_tag = link_tag or self.bootstrap_link_tag
         
        # Ensure that the previous page and next page buttons are displayed
        if self.previous_page is None:
            self.previous_page = self.first_page

        if self.next_page is None:
            self.next_page = self.last_page         
         
        return literal(super(BootStrapPage, self).pager(format=format, url=url,
            show_if_single_page=show_if_single_page, separator=separator,
            symbol_first=symbol_first, symbol_last=symbol_last,
            symbol_previous=symbol_previous, symbol_next=symbol_next,
            link_attr=link_attr, curpage_attr=curpage_attr,
            dotdot_attr=dotdot_attr, link_tag=link_tag))
        
    def link_map(self, format='~2~', url=None, show_if_single_page=False,
        separator=' ', symbol_first='&lt;&lt;', symbol_last='&gt;&gt;',
        symbol_previous='&lt;', symbol_next='&gt;', link_attr=dict(),
        curpage_attr=dict(), dotdot_attr=dict()):
        
        nmap = super(BootStrapPage, self).link_map(format=format, url=url,
            show_if_single_page=show_if_single_page, separator=separator,
            symbol_first=symbol_first, symbol_last=symbol_last,
            symbol_previous=symbol_previous, symbol_next=symbol_next,
            link_attr=link_attr, curpage_attr=curpage_attr,
            dotdot_attr=dotdot_attr)
        
        # Check if we are in the first or last page
        if nmap['previous_page']['number'] <= nmap['first_page']['number']:
            nmap['previous_page']['number'] = None
            nmap['previous_page']['href'] = '#'
        
        if nmap['next_page']['number'] >= nmap['last_page']['number']:
            nmap['next_page']['number'] = None
            nmap['next_page']['href'] = '#'
                    
        # Remove the dots
        navmap = {}
        for key in nmap:
            if key != 'range_pages':
                navmap[key] = nmap[key]
            else:
                navmap['range_pages'] = []
                for page in nmap['range_pages']:
                    if page['value'] != '..':
                        navmap['range_pages'].append(page)
            
        return navmap
        
    @staticmethod
    def bootstrap_link_tag(item):
        link_attr = {}
        if item['number'] is None:
            link_attr = {'class': 'disabled'}

        if item['type'] == 'current_page':
            link_attr = {'class': 'active'}

        #logger.info("item: {}".format(item))

        item['attrs'] = { 'class':'pager_link' }

        return HTML.li(literal(paginate.Page.default_link_tag(item)),
            **link_attr)



def create_pagination_mongo_collection(request, cursor, cursor_size,
    items_per_page=10):
    
    def page_url(page):
        if page is None:
            return '#'
        if request.query_string:
            try:
                indexOf = request.query_string.index('&page')
            except ValueError:
                indexOf = len(request.query_string)
            return '%s?%s&page=%s' % (request.path,
                request.query_string[:indexOf], page)
        else:
            return '%s?page=%s' % (request.path, page)
    
    current_page = int(request.GET.get('page', 1))
    page = BootStrapPage(range(cursor_size),
                         current_page,
                         url_maker=page_url,
                         items_per_page=items_per_page)
    # Limits the records to the page
    cursor[(current_page - 1) * items_per_page:current_page * items_per_page]
    return page
