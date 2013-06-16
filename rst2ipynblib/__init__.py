"""
Simple ipython notebook document tree Writer.

"""

__docformat__ = 'reStructuredText'

import ipython_console_highlighting

import sys
import os
import os.path
import time
import re
import urllib
import docutils
from docutils import frontend, nodes, utils, writers, languages, io
from docutils.transforms import writer_aux
try:
    from docutils.math import unichar2tex, pick_math_environment
    from docutils.math.latex2mathml import parse_latex_math
    from docutils.math.math2html import math2html
except ImportError:
    from docutils.utils.math import unichar2tex, pick_math_environment
    from docutils.utils.math.latex2mathml import parse_latex_math
    from docutils.utils.math.math2html import math2html

try:
    from docutils.utils.error_reporting import SafeString
except ImportError:
    from docutils.error_reporting import SafeString

from IPython.nbformat import current as nbformat
import pypandoc

# the ipython prompt regular expression
IPYPROMPT = re.compile(r"(?P<prompt>In \[[0-9]+\]:)(?P<code>.*)")


class Writer(writers.Writer):

    supported = ('ipynb')
    """Formats this writer supports."""

    visitor_attributes = ()

    def get_transforms(self):
        return writers.Writer.get_transforms(self) + [writer_aux.Admonitions]

    def __init__(self):
        writers.Writer.__init__(self)
        self.translator_class = IPYNBTranslator

    def translate(self):
        self.visitor = visitor = self.translator_class(self.document)
        self.document.walkabout(visitor)
        for attr in self.visitor_attributes:
            setattr(self, attr, getattr(visitor, attr))
        self.output = '{0}'.format(nbformat.writes(visitor.nb, 'ipynb'))


class IPYNBTranslator(nodes.GenericNodeVisitor):

    """
    """

    def __init__(self, document):
        nodes.NodeVisitor.__init__(self, document)
        self.settings = settings = document.settings
        lcode = settings.language_code
        self.language = languages.get_language(lcode, document.reporter)
        # A heterogenous stack used in conjunction with the tree traversal.
        # Make sure that the pops correspond to the pushes:
        self.context = []
        self.body = []
        self.section_level = 0
        self.list_item_level = 0
        self.current_list = None
        ws = nbformat.new_worksheet()
        self.nb = nbformat.new_notebook(worksheets=[ws])

    def astext(self):
        return '{0}'.format(nbformat.writes(self.nb, 'ipynb'))

    def is_ref_error_paragraph(self, p):
        return p == "Unknown interpreted text role \"ref\"."

    def strip_elipsis(self, code):
        search = ['# doctest: +ELLIPSIS', '# doctest: +SKIP']
        for s in search:
            if code.endswith(s):
                return code[:-len(s)]
        else:
            return code

    def add_cell(self, cell):
        self.nb.worksheets[0].cells.append(cell)

    def add_markdown_cell(self, source):
        cell = nbformat.new_text_cell('markdown',
                source=source)
        self.add_cell(cell)

    def add_code_cell(self, lines):
        cell = nbformat.new_code_cell(input='\n'.join(lines))
        self.add_cell(cell)

    def add_raw_cell(self, source):
        cell = nbformat.new_text_cell('raw',
                source=source)
        self.add_cell(cell)

    def visit_literal_block(self, node):
        if self.list_item_level > 0:
            self.add_list_cell()
            self.current_list = []
            self.list_item_level = 1
        raw_text = node.astext()
        language = node['language'] if node.has_key('language') else None
        current_cell = []
        if language is not None and language in ['pycon', 'ipython']:
            for line in raw_text.split('\n'):
                ipyprompt = IPYPROMPT.match(line)
                # try matching the >>> prompt
                if line.startswith('>>>'):
                    code = line.split('>>>')[1][1:]
                    current_cell.append(self.strip_elipsis(code))
                elif line.startswith('...'):
                    code = line.split('...')[1][1:]
                    current_cell.append(self.strip_elipsis(code))
                # try matching ipypromt
                elif ipyprompt is not None:
                    current_cell.append(ipyprompt.groupdict()['code'].strip())
                # some kind of output
                elif current_cell:
                    self.add_code_cell(current_cell)
                    current_cell = []
        else:
            self.add_raw_cell(raw_text)
        # if the last line was not output
        if current_cell:
            self.add_code_cell(current_cell)

    def visit_paragraph(self, node):
        text = node.astext()
        # For every ref directive a paragraph contains
        # docutils will generate a paragraph complaining
        # "Unknown interpreted text role \"ref\"."
        # this is because ref is a sphinx directive
        # that does not exist in docutils
        # looking for a better way to handle this
        # for now filtering such pargraphs from the output
        if not self.is_ref_error_paragraph(text):
            encoded = node.rawsource.encode('utf8')
            md = pypandoc.convert(encoded, 'md', format='rst').decode('utf8')
            if self.list_item_level > 0:
                self.add_list_item(md)
            else:
                self.add_markdown_cell(md)

    def visit_bullet_list(self, node):
        if self.list_item_level == 0:
            self.current_list = []
        self.list_item_level += 1
        self.default_visit(node)

    def depart_bullet_list(self, node):
        if self.list_item_level > 0:
            self.list_item_level -= 1
        if self.list_item_level == 0:
            self.add_list_cell()
        self.default_departure(node)

    def add_list_item(self, item):
        self.current_list.append("%s* %s" %
                ((self.list_item_level - 1) * "    ", item))

    def add_list_cell(self):
        self.add_markdown_cell("\n".join(self.current_list))
        self.current_list = None

    def visit_list_item(self, node):
        self.default_visit(node)

    def depart_list_item(self, node):
        self.default_departure(node)

    def visit_section(self, node):
        self.section_level += 1
        self.default_visit(node)

    def depart_section(self, node):
        self.section_level -= 1
        self.default_departure(node)

    def visit_title(self, node):
        #make sure we have a valid heading level between 1 and 6
        heading_level = min(self.section_level, 5) + 1
        h = nbformat.new_heading_cell(source=node.astext(),
                                      level=heading_level)
        self.add_cell(h)

    def default_visit(self, node):
        node_class = node.__class__.__name__
        #print '*default_visit', node_class
        #if node_class in ['reference','paragraph','literal_block','title']:
        if node_class in []:
            print '*default_visit', node_class
            print node.astext()

    def default_departure(self, node):
        #print '*default depart', node.__class__.__name__
        pass
