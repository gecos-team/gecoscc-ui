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

import webhelpers.paginate as paginate


from webhelpers.html import HTML, literal

from string import Template
import re


class BootStrapPage(paginate.Page):

    def pager(self, link_format='$link_previous ~2~ $link_next', page_param='page', partial_param='partial',
              show_if_single_page=False, separator=' ', onclick=None,
              symbol_first='<<', symbol_last='>>',
              symbol_previous=u'«', symbol_next=u'»',
              link_attr={'class': 'pager_link'}, curpage_attr={'class': 'pager_curpage'},
              dotdot_attr={'class': 'pager_dotdot'}, **kwargs):
        self.curpage_attr = curpage_attr
        self.separator = separator
        self.pager_kwargs = kwargs
        self.page_param = page_param
        self.partial_param = partial_param
        self.onclick = onclick
        self.link_attr = link_attr
        self.dotdot_attr = dotdot_attr

        # Don't show navigator if there is no more than one page
        if self.page_count == 0 or (self.page_count == 1 and not show_if_single_page):
            return ''

        # Replace ~...~ in token format by range of pages
        result = re.sub(r'~(\d+)~', self._range, link_format)

        # Interpolate '%' variables
        result = Template(result).safe_substitute({
            'first_page': self.first_page,
            'last_page': self.last_page,
            'page': self.page,
            'page_count': self.page_count,
            'items_per_page': self.items_per_page,
            'first_item': self.first_item,
            'last_item': self.last_item,
            'item_count': self.item_count,
            'link_first': (self.page > self.first_page and
                           self._pagerlink(self.first_page, symbol_first) or ''),
            'link_last': (self.page < self.last_page and
                          self._pagerlink(self.last_page, symbol_last) or ''),
            'link_previous': self._pagerlink(self.previous_page, symbol_previous),
            'link_next': self._pagerlink(self.next_page, symbol_next)
        })

        return literal(result)

    def _range(self, regexp_match):
        radius = int(regexp_match.group(1))

        # Compute the first and last page number within the radius
        # e.g. '1 .. 5 6 [7] 8 9 .. 12'
        # -> leftmost_page  = 5
        # -> rightmost_page = 9
        leftmost_page = max(self.first_page, (self.page - radius))
        rightmost_page = min(self.last_page, (self.page + radius))

        nav_items = []

        # Create a link to the first page (unless we are on the first page
        # or there would be no need to insert '..' spacers)
        if self.page != self.first_page and self.first_page < leftmost_page:
            nav_items.append(self._pagerlink(self.first_page, self.first_page))

        for thispage in xrange(leftmost_page, rightmost_page + 1):
            # Hilight the current page number and do not use a link
            if thispage == self.page:
                text = '%s' % (thispage,)
                # Wrap in a SPAN tag if nolink_attr is set
                if self.curpage_attr:
                    text = self._pagerlink(thispage, text, link_attr={'class': 'active'})
                nav_items.append(text)
            # Otherwise create just a link to that page
            else:
                text = '%s' % (thispage,)
                nav_items.append(self._pagerlink(thispage, text))

        # Create a link to the very last page (unless we are on the last
        # page or there would be no need to insert '..' spacers)
        if self.page != self.last_page and rightmost_page < self.last_page:
            nav_items.append(self._pagerlink(self.last_page, self.last_page))

        return self.separator.join(nav_items)

    def _pagerlink(self, page, text, link_attr=None):
        link_attr = link_attr or {}
        if not page:
            link_attr = {'class': 'disabled'}
        return HTML.li(super(BootStrapPage, self)._pagerlink(page, text), **link_attr)


def create_pagination_mongo_collection(request, collection, items_per_page=10):
    def page_url(page):
        if page is None:
            return '#'
        if request.query_string:
            try:
                indexOf = request.query_string.index('&page')
            except ValueError:
                indexOf = len(request.query_string)
            return '%s?%s&page=%s' % (request.path, request.query_string[:indexOf], page)
        else:
            return '%s?page=%s' % (request.path, page)
    current_page = int(request.GET.get('page', 1))
    page = BootStrapPage(range(collection.count()),
                         current_page,
                         url=page_url,
                         items_per_page=items_per_page)
    collection[(current_page - 1) * items_per_page:current_page * items_per_page]
    return page
