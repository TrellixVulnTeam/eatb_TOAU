#!/usr/bin/env python
# -*- coding: utf-8 -*-
import lxml


class ParsedMets():
    """
    Parsed METS object
    """
    ns = {'mets': 'http://www.loc.gov/METS/', 'xlink': 'http://www.w3.org/1999/xlink',
          'xsi': 'http://www.w3.org/2001/XMLSchema-instance'}

    mets_tree = None

    def __init__(self, rdir):
        """
        Constructor takes root directory as argument; paths in METS file are relative to this directory.

        @type       rdir: string
        @param      rdir: Path to root directory
        """
        self.root_dir = rdir
        self.mets_tree = None

    def set_parsed_mets(self, pmets):
        """
        Set mets ElementTree object which is parsed already

        @type       pmets: ElementTree
        @param      pmets: Parsed METS
        """
        self.mets_tree = pmets

    def load_mets(self, mets_file_path):
        """
        Load mets Element tree object

        @type       pmets: ElementTree
        @param      pmets: Parsed METS
        """
        self.mets_tree = lxml.etree.parse(mets_file_path)

    def get_root(self):
        if self.mets_tree is None:
            raise ValueError("Attribute 'mets_tree' of type ElementTree must be initialized")
        return self.mets_tree.getroot()

    def get_file_elements(self):
        return self.mets_tree.getroot().xpath('/mets:mets/mets:fileSec/mets:fileGrp/mets:file', namespaces=ParsedMets.ns)

    def get_first_file_element(self):
        file_elements = self.get_file_elements()
        if len(file_elements) > 0:
            return file_elements[0]
        return None

    @staticmethod
    def get_file_element_checksum(file_element):
        return ''.join(file_element.xpath('@CHECKSUM'))

    @staticmethod
    def get_file_element_checksum_algorithm(file_element):
        return ''.join(file_element.xpath('@CHECKSUMTYPE'))

    @staticmethod
    def get_file_element_reference(file_element):
        return ''.join(file_element.xpath('mets:FLocat/@xlink:href', namespaces=ParsedMets.ns))

    def get_obj_id(self):
        xpath_result = self.mets_tree.getroot().xpath('@OBJID', namespaces=ParsedMets.ns)
        return xpath_result[0] if len(xpath_result) == 1 else "urn:uuid:none"

    def get_package_type(self):
        xpath_result = self.mets_tree.getroot().xpath('@TYPE', namespaces=ParsedMets.ns)
        return xpath_result[0] if len(xpath_result) == 1 else "NONE"

    def get_mets_schema_from_schema_location(self):
        if self.mets_tree is None:
            raise ValueError("Attribute 'mets_tree' of type ElementTree must be initialized")
        root = self.mets_tree.getroot()
        schema_file = ''
        locations = root.xpath('/mets:mets/@xsi:schemaLocation', namespaces=ParsedMets.ns)
        locations = ''.join(locations)
        locations = locations.split(' ')
        for token in locations:
            if token == ('http://www.loc.gov/METS/'):
                position = locations.index(token)
                schema_location = locations[position + 1]
                if schema_location.startswith(''):
                    schema_file = self.root_dir + schema_location
        return schema_file
