#!/usr/bin/env python
# -*- coding: utf-8 -*-
import fnmatch
import logging
from mimetypes import MimeTypes
import os
from subprocess import Popen, PIPE
import uuid

from lxml import etree, objectify

from eatb.storage.checksum import get_sha256_hash
from eatb.utils.datetime import get_file_ctime_iso_date_str, DT_ISO_FMT_SEC_PREC, current_timestamp
from eatb.format.formatidentification import FormatIdentification
from eatb.metadata.XmlHelper import q, XSI_NS
from eatb.settings import application_name, application_version

METS_NS = 'http://www.loc.gov/METS/'
METSEXT_NS = 'ExtensionMETS'
XLINK_NS = "http://www.w3.org/1999/xlink"
CSIP_NS = "https://DILCIS.eu/XML/METS/CSIPExtensionMETS"
METS_NSMAP = {None: METS_NS, "csip": CSIP_NS, "xlink": "http://www.w3.org/1999/xlink", "ext": METSEXT_NS,
              "xsi": "http://www.w3.org/2001/XMLSchema-instance"}
DELIVERY_METS_NSMAP = {None: METS_NS, "csip": CSIP_NS, "xlink": "http://www.w3.org/1999/xlink",
                       "xsi": "http://www.w3.org/2001/XMLSchema-instance"}
PROFILE_XML = "https://earkcsip.dilcis.eu/profile/E-ARK-CSIP.xml"

default_mets_schema_location = 'schemas/mets.xsd'
default_csip_location = "schemas/DILCISExtensionMETS.xsd"
default_xlink_schema_location = 'https://www.w3.org/1999/xlink.xsd'

M = objectify.ElementMaker(
    annotate=False,
    namespace=METS_NS,
    nsmap=METS_NSMAP)

folders_with_USE = ['documentation', 'schemas', 'representations', "data"]

logger = logging.getLogger(__name__)


def get_folder_with_USE(path):
    try:
        dirs = path.split('/')
        for dir in dirs[::-1]:
            if dir in folders_with_USE:
                return dir
    except Exception as e:
        logger.debug('Parent directory not used')
        logger.debug(e)
    return 'other'


class MetsGenerator(object):
    '''
    This class generates a Mets file.
    It has to be instantiated (something = MetsGenerator(path) with the (A/S)IP root path as an argument (to specify
    the Mets directory; all subfolders will be treated as part of the IP. After this. the createMets can be called
    (something.createMets(data)) with a dictionary that must contain 'packageid', 'schemas' (location of the schema
    folder) and 'type', where 'type' must comply with the Mets standard for TYPE attribute of the Mets root.
    '''

    fid = FormatIdentification()
    mime = MimeTypes()
    root_path = ""
    mets_data = None

    def __init__(self, root_path):
        self.root_path = root_path

    def runCommand(self, program, stdin=PIPE, stdout=PIPE, stderr=PIPE):
        result, res_stdout, res_stderr = None, None, None
        try:
            # quote the executable otherwise we run into troubles
            # when the path contains spaces and additional arguments
            # are presented as well.
            # special: invoking bash as login shell here with
            # an unquoted command does not execute /etc/profile

            logger.debug('Launching: ' + ' '.join(program))
            process = Popen(program, stdin=stdin, stdout=stdout, stderr=stderr, shell=False)

            res_stdout, res_stderr = process.communicate()
            result = process.returncode
            logger.debug('Finished: ' + ' '.join(program))

        except Exception as ex:
            res_stderr = ''.join(str(ex.args))
            result = 1

        if result != 0:
            logger.debug('Command failed:' + ''.join(res_stderr))
            raise Exception('Command failed:' + ''.join(res_stderr))

        return result, res_stdout, res_stderr

    def createAgent(self,role, type, other_type, name, note, notetype=None):
        if other_type:
#            agent = M.agent({"ROLE": role, "TYPE": type, "OTHERTYPE": other_type}, M.name(name), M.note({q(CSIP_NS, "NOTETYPE"): notetype}, note))
            agent = M.agent({"ROLE": role, "TYPE": type, "OTHERTYPE": other_type}, M.name(name), M.note(note, {q(CSIP_NS, "NOTETYPE"): "SOFTWARE VERSION"}))
        else:
            agent = M.agent({"ROLE": role, "TYPE": type}, M.name(name), M.note(note), M.note(note, {q(CSIP_NS, "NOTETYPE"): "SOFTWARE VERSION"}))
        return agent

    def addFile(self, file_name, mets_filegroup):
        # reload(sys)
        # sys.setdefaultencoding('utf8')
        file_url = "%s" % os.path.relpath(file_name, self.root_path)
        file_mimetype, _ = self.mime.guess_type(file_url)
        file_mimetype = file_mimetype if file_mimetype else "application/octet-stream"
        file_checksum = get_sha256_hash(file_name)
        file_size = os.path.getsize(file_name)
        file_cdate = get_file_ctime_iso_date_str(file_name, DT_ISO_FMT_SEC_PREC)
        file_id = "ID" + uuid.uuid4().__str__()
        mets_file = M.file(
            {"MIMETYPE": file_mimetype, "CHECKSUMTYPE": "SHA-256", "CREATED": file_cdate, "CHECKSUM": file_checksum,
             "USE": "Datafile", "ID": file_id, "SIZE": file_size})
        mets_filegroup.append(mets_file)
        # _,fname = os.path.split(file_name)
        mets_FLocat = M.FLocat({q(XLINK_NS, 'href'): file_url, "LOCTYPE": "URL", q(XLINK_NS, 'type'): 'simple'})
        mets_file.append(mets_FLocat)
        return file_id

    def addFiles(self, folder, mets_filegroup):
        ids = []
        for top, dirs, files in os.walk(folder):
            for fn in files:
                file_name = os.path.join(top, fn)
                file_id = self.addFile(file_name, mets_filegroup)
                ids.append(file_id)
        return ids

    def make_mdref(self, path, file, id, mdtype):
        mimetype, _ = self.mime.guess_type(os.path.join(path, file))
        mimetype = mimetype if mimetype else "application/octet-stream"
        rel_path = "%s" % os.path.relpath(os.path.join(path, file), self.root_path)
        mets_mdref = {"LOCTYPE": "URL",
                      "MIMETYPE": mimetype,
                      "CREATED": current_timestamp(),
                      q(XLINK_NS, "type"): "simple",
                      q(XLINK_NS, "href"): rel_path,
                      "CHECKSUMTYPE": "SHA-256",
                      "CHECKSUM": get_sha256_hash(os.path.join(path, file)),
                      "ID": id,
                      "SIZE": os.path.getsize(os.path.join(path, file)),
                      "MDTYPE": mdtype}
        return mets_mdref

    def setParentRelation(self, identifier):
        parentmets = os.path.join(self.root_path, 'METS.xml')
        packagetype = self.mets_data['type']
        if os.path.exists(parentmets):
            parser = etree.XMLParser(resolve_entities=False, remove_blank_text=True, strip_cdata=False)
            parent_parse = etree.parse(parentmets, parser)
            parent_root = parent_parse.getroot()

            parent = M.div({'LABEL': "parent %s" % packagetype})
            pointer = M.mptr({"LOCTYPE": "OTHER",
                              "OTHERLOCTYPE": "UUID",
                              q(XLINK_NS, "title"): ("Referencing a parent %s." % packagetype),
                              q(XLINK_NS, "href"): identifier,
                              "ID": "ID" + uuid.uuid4().__str__()})
            parent.append(pointer)

            parent_map = parent_root.find("%s[@LABEL='parent %s']" % (q(METS_NS, 'structMap'), packagetype))
            if parent_map is not None:
                parent_div = parent_map.find("%s[@LABEL='parent %s identifiers']" % (q(METS_NS, 'div'), packagetype))
                parent_div.append(parent)
            else:
                parent_map = M.structMap({'LABEL': 'parent %s' % packagetype, 'TYPE': 'logical'})
                parent_div = M.div({'LABEL': 'parent %s identifiers' % packagetype})
                parent_map.append(parent_div)
                parent_div.append(parent)
                parent_root.insert(len(parent_root), parent_map)

            str = etree.tostring(parent_root, encoding='UTF-8', pretty_print=True, xml_declaration=True)
            with open(parentmets, 'w') as output_file:
                output_file.write(str)
        else:
            logger.debug('Couldn\'t find the parent %ss Mets file.' % packagetype)

    def addChildRelation(self, identifier):
        parentmets = os.path.join(self.root_path, 'METS.xml')
        packagetype = self.mets_data['type']
        if os.path.exists(parentmets):
            parser = etree.XMLParser(resolve_entities=False, remove_blank_text=True, strip_cdata=False)
            parent_parse = etree.parse(parentmets, parser)
            parent_root = parent_parse.getroot()
            child = M.div({'LABEL': "child %s" % packagetype})
            pointer = M.mptr({"LOCTYPE": "OTHER",
                              "OTHERLOCTYPE": "UUID",
                              q(XLINK_NS, "title"): ("Referencing a child %s." % packagetype),
                              q(XLINK_NS, "href"): identifier,
                              "ID": "ID" + uuid.uuid4().__str__()})
            child.append(pointer)

            children_map = parent_root.find("%s[@LABEL='child %s']" % (q(METS_NS, 'structMap'), packagetype))
            if children_map is not None:
                children_div = children_map.find("%s[@LABEL='child %s identifiers']" % (q(METS_NS, 'div'), packagetype))
                children_div.append(child)
            else:
                children_map = M.structMap({'LABEL': 'child %s' % packagetype, 'TYPE': 'logical'})
                children_div = M.div({'LABEL': 'child %s identifiers' % packagetype})
                children_map.append(children_div)
                children_div.append(child)
                parent_root.insert(len(parent_root), children_map)

            str = etree.tostring(parent_root, encoding='UTF-8', pretty_print=True, xml_declaration=True)
            with open(parentmets, 'w') as output_file:
                output_file.write(str)
        else:
            logger.debug('Couldn\'t find the parent %ss Mets file.' % packagetype)

    def createMets(self, mets_data, mets_file_path=None):
        self.mets_data = mets_data
        packageid = mets_data['packageid']
        packagetype = mets_data['type']
        schemafolder = mets_data['schemas']
        parent = mets_data['parent']

        ###########################
        # create METS skeleton
        ###########################

        # create Mets root
        METS_ATTRIBUTES = {"OBJID": packageid,
                           "LABEL": "METS file describing the %s matching the OBJID." % packagetype,
                           "PROFILE": PROFILE_XML,
                           "TYPE": "Databases",
                           q(CSIP_NS, "CONTENTINFORMATIONTYPE"): "SIARD2"}
        root = M.mets(METS_ATTRIBUTES)

        if os.path.isfile(os.path.join(schemafolder, 'mets.xsd')):
            mets_schema_location = os.path.relpath(os.path.join(schemafolder, 'mets.xsd'), self.root_path)
        else:
            mets_schema_location = default_mets_schema_location
        if os.path.isfile(os.path.join(schemafolder, 'xlink.xsd')):
            xlink_schema_location = os.path.relpath(os.path.join(schemafolder, 'xlink.xsd'), self.root_path)
        else:
            xlink_schema_location = default_xlink_schema_location

        root.attrib['{%s}schemaLocation' % XSI_NS] = "%s %s " \
                                                     "%s %s " \
                                                     "%s %s" % \
                                                     (METS_NS, mets_schema_location,
                                                      XLINK_NS, xlink_schema_location,
                                                      CSIP_NS, default_csip_location)

        # create Mets header
        mets_hdr = M.metsHdr({"CREATEDATE": current_timestamp(), "RECORDSTATUS": "NEW", q(CSIP_NS, "OAISPACKAGETYPE"): packagetype})
        root.append(mets_hdr)

        # add an agent
        mets_hdr.append(self.createAgent("CREATOR", "OTHER", "SOFTWARE", application_name, "VERSION=%s" % application_version, "SOFTWARE VERSION"))
        mets_hdr.append(M.agent({"ROLE": "ARCHIVIST", "TYPE": "ORGANIZATION"}, M.name("E-ARK")))
        mets_hdr.append(M.agent({"ROLE": "CREATOR", "TYPE": "ORGANIZATION"}, M.name("E-ARK")))
        mets_hdr.append(M.agent({"ROLE": "PRESERVATION", "TYPE": "ORGANIZATION"}, M.name("E-ARK")))

        # add document ID
        mets_hdr.append(M.metsDocumentID("METS.xml"))

        # create amdSec
        mets_amdSec = M.amdSec({"ID": "ID" + uuid.uuid4().__str__()})
        root.append(mets_amdSec)

        # create fileSec
        mets_fileSec = M.fileSec({"ID": "ID" + uuid.uuid4().__str__()})
        root.append(mets_fileSec)

        # filegroups
        mets_filegroups = dict()

        folder_with_USE = get_folder_with_USE(self.root_path)
        mets_filegroups[folder_with_USE] = M.fileGrp({"ID": "ID" + uuid.uuid4().__str__(), "USE": folder_with_USE})
        # for METSs in subfolders
        for subdir in next(os.walk(self.root_path))[1]:
            if subdir in folders_with_USE:
                mets_filegroups[subdir] = M.fileGrp({"ID": "ID" + uuid.uuid4().__str__(), "USE": subdir})
                mets_fileSec.append(mets_filegroups[subdir])

        # structMap 'CSIP' - default, physical structure
        mets_earkstructmap = M.structMap({"LABEL": "CSIP", "TYPE": "PHYSICAL", "ID": "ID" + uuid.uuid4().__str__()})
        root.append(mets_earkstructmap)
        package_div = M.div({"LABEL": packageid, "ID": "ID" + uuid.uuid4().__str__()})
        # append physical structMap
        mets_earkstructmap.append(package_div)

        # structMap and div for the whole package (metadata, schema and /data)
        mets_structmap = M.structMap({"LABEL": "Simple %s structuring" % packagetype, "TYPE": "logical", "ID": "ID" + uuid.uuid4().__str__()})
        root.append(mets_structmap)
        mets_structmap_div = M.div({"LABEL": "Package structure", "ID": "ID" + uuid.uuid4().__str__()})
        mets_structmap.append(mets_structmap_div)

        # metadata structmap - IP root level!
        mets_structmap_metadata_div = M.div({"LABEL": "metadata files", "ID": "ID" + uuid.uuid4().__str__()})
        mets_structmap_div.append(mets_structmap_metadata_div)

        # structmap for schema files
        mets_structmap_schema_div = M.div({"LABEL": "schema files", "ID": "ID" + uuid.uuid4().__str__()})
        mets_structmap_div.append(mets_structmap_schema_div)

        # content structmap - all representations! (is only filled if no separate METS exists for the rep)
        mets_structmap_content_div = M.div({"LABEL": "content files", "ID": "ID" + uuid.uuid4().__str__()})
        mets_structmap_div.append(mets_structmap_content_div)

        # create structmap and div for Mets files from representations
        # mets_structmap_reps = M.structMap({"TYPE": "logical", "LABEL": "representations"})
        # root.append(mets_structmap_reps)
        # mets_div_reps = M.div({"LABEL": "representations", "TYPE": "type"})
        # mets_structmap_reps.append(mets_div_reps)

        # create structmap for parent/child relation, if applicable
        if parent and parent != '':
            logger.debug('creating link to parent %s' % packagetype)
            mets_structmap_relation = M.structMap({'TYPE': 'logical', 'LABEL': 'parent'})
            root.append(mets_structmap_relation)
            mets_div_rel = M.div({'LABEL': '%s parent identifier' % packagetype, "ID": "ID" + uuid.uuid4().__str__()})
            mets_structmap_relation.append(mets_div_rel)
            parent_pointer = M.mptr({"LOCTYPE": "OTHER",
                                     "OTHERLOCTYPE": "UUID",
                                     q(XLINK_NS, "title"): ("Referencing the parent %s of this (%s) %s." % (packagetype, packageid, packagetype)),
                                     q(XLINK_NS, "href"): parent,
                                     "ID": "ID" + uuid.uuid4().__str__()})
            mets_div_rel.append(parent_pointer)

        ###########################
        # add to Mets skeleton
        ###########################

        # add the package content to the Mets skeleton
        for directory, subdirectories, filenames in os.walk(self.root_path):
            folder_with_USE = get_folder_with_USE(directory)
            # build the earkstructmap
            path = os.path.relpath(directory, self.root_path)
            physical_div = ''
            if path != 'representations': # otherwise an empty div is created
                if path != '.':
                    physical_div = M.div({"LABEL": path, "ID": "ID" + uuid.uuid4().__str__()})
                    package_div.append(physical_div)
                # if directory.endswith('metadata/conduit'):
                #     # Ignore temp files only needed for IP processing with conduit
                #     del filenames[:]
                #     del subdirectories[:]
                if directory.endswith('/metadata'):
                    del filenames[:]
                    del subdirectories[:]
                if directory == os.path.join(self.root_path, 'metadata'):
                    # Metadata on IP root level - if there are folders for representation-specific metadata,
                    # check if the corresponding representation has a Mets file. If yes, skip; if no, add to IP root Mets.
                    for filename in filenames:
                        if filename == 'conduit.log':
                            mets_digiprovmd = M.digiprovMD({"ID": "ID" + uuid.uuid4().__str__()})
                            mets_amdSec.append(mets_digiprovmd)
                            id = "ID" + uuid.uuid4().__str__()
                            ref = self.make_mdref(directory, filename, id, 'OTHER')
                            mets_mdref = M.mdRef(ref)
                            mets_digiprovmd.append(mets_mdref)
                            mets_structmap_metadata_div.append(M.fptr({"FILEID": id}))
                            physical_div.append(M.fptr({"FILEID": id}))
                    del subdirectories[:]  # prevent loop to iterate subfolders outside of this if statement
                    dirlist = os.listdir(os.path.join(self.root_path, 'metadata'))
                    for dirname in dirlist:
                        if fnmatch.fnmatch(dirname, '*_mig-*'):
                            # TODO: maybe list it all the time?
                            # this folder contains metadata for a representation/migration, currently:
                            # only listed if no representation Mets file exists
                            if os.path.isfile(os.path.join(self.root_path, 'representations/%s/METS.xml') % dirname):
                                pass
                            else:
                                for dir, subdir, files in os.walk(os.path.join(self.root_path, 'metadata/%s') % dirname):
                                    for filename in files:
                                        if dir.endswith('descriptive'):
                                            mets_dmd = M.dmdSec({"ID": "ID" + uuid.uuid4().__str__(), "CREATED": current_timestamp(), "STATUS": "CURRENT"})
                                            root.insert(1, mets_dmd)
                                            id = "ID" + uuid.uuid4().__str__()
                                            ref = self.make_mdref(dir, filename, id, 'OTHER')
                                            mets_mdref = M.mdRef(ref)
                                            mets_dmd.append(mets_mdref)
                                            mets_structmap_metadata_div.append(M.fptr({"FILEID": id}))
                                            physical_div.append(M.fptr({"FILEID": id}))
                                        elif dir.endswith('preservation'):
                                            mets_digiprovmd = M.digiprovMD({"ID": "ID" + uuid.uuid4().__str__()})
                                            mets_amdSec.append(mets_digiprovmd)
                                            id = "ID" + uuid.uuid4().__str__()
                                            mdtype = ''
                                            if filename.startswith('premis') or filename.endswith('premis.xml'):
                                                mdtype = 'PREMIS'
                                            else:
                                                mdtype = 'OTHER'
                                            ref = self.make_mdref(dir, filename, id, mdtype)
                                            mets_mdref = M.mdRef(ref)
                                            mets_digiprovmd.append(mets_mdref)
                                            mets_structmap_metadata_div.append(M.fptr({"FILEID": id}))
                                            physical_div.append(M.fptr({"FILEID": id}))
                                        elif filename:
                                            logger.debug('Unclassified metadata file %s in %s.' % (filename, dir))
                        else:
                            # metadata that should be listed in the Mets
                            for dir, subdir, files in os.walk(os.path.join(self.root_path, 'metadata/%s') % dirname):
                                if len(files) > 0:
                                    for filename in files:
                                        #if dir.endswith('descriptive'):
                                        if dirname == 'descriptive':
                                            mets_dmd = M.dmdSec({"ID": "ID" + uuid.uuid4().__str__(), "CREATED": current_timestamp(), "STATUS": "CURRENT"})
                                            root.insert(1, mets_dmd)
                                            id = "ID" + uuid.uuid4().__str__()
                                            # TODO: change MDTYPE
                                            ref = self.make_mdref(dir, filename, id, 'OTHER')
                                            mets_mdref = M.mdRef(ref)
                                            mets_dmd.append(mets_mdref)
                                            mets_structmap_metadata_div.append(M.fptr({"FILEID": id}))
                                            physical_div.append(M.fptr({"FILEID": id}))
                                        #elif dir.endswith('preservation'):
                                        elif dirname == 'preservation' or dirname == 'conduit':
                                            mets_digiprovmd = M.digiprovMD({"ID": "ID" + uuid.uuid4().__str__(), "STATUS": "CURRENT"})
                                            mets_amdSec.append(mets_digiprovmd)
                                            id = "ID" + uuid.uuid4().__str__()
                                            mdtype = ''
                                            if filename.startswith('premis') or filename.endswith('premis.xml'):
                                                mdtype = 'PREMIS'
                                            elif filename:
                                                mdtype = 'OTHER'
                                            ref = self.make_mdref(dir, filename, id, mdtype)
                                            mets_mdref = M.mdRef(ref)
                                            mets_digiprovmd.append(mets_mdref)
                                            mets_structmap_metadata_div.append(M.fptr({"FILEID": id}))
                                            physical_div.append(M.fptr({"FILEID": id}))
                                        elif filename:
                                            logger.debug('Unclassified metadata file %s in %s.' % (filename, dir))
                else:
                    # Any other folder outside of /<root>/metadata
                    for filename in filenames:
                        if directory == self.root_path:
                            # ignore files on IP root level
                            del filename
                        else:
                            # TODO: list rep metadata only in the rep Mets?
                            rel_path_file = "%s" % os.path.relpath(os.path.join(directory, filename), self.root_path)
                            if filename.lower() == 'mets.xml':
                                # delete the subdirectories list to stop os.walk from traversing further;
                                # mets file should be added as <mets:mptr> to <structMap> for corresponding rep
                                del subdirectories[:]
                                rep_name = directory.rsplit('/', 1)[1]
                                # create structMap div and append to representations structMap
                                # mets_structmap_rep_div = M.div({"LABEL": rep_name, "TYPE": "representation mets", "ID": "ID" + uuid.uuid4().__str__()})
                                # mets_div_reps.append(mets_structmap_rep_div)
                                # add mets file as <mets:mptr>
                                metspointer = M.mptr({"LOCTYPE": "URL",
                                                      q(XLINK_NS, "title"): ("Mets file describing representation: %s of %s: urn:uuid:%s." % (rep_name, packagetype, packageid)),
                                                      q(XLINK_NS, "href"): rel_path_file,
                                                      q(XLINK_NS, 'type'): 'simple',
                                                      "ID": "ID" + uuid.uuid4().__str__()})
                                #mets_structmap_rep_div.append(metspointer)
                                #mets_structmap_rep_div.append(M.fptr({"FILEID": id}))
                                physical_div.append(metspointer)    # IMPORTANT: The <mptr> element needs to be the first entry in a <div>, or the Mets will be invalid!
                                # also create a <fptr> for the Mets file
                                id = self.addFile(os.path.join(directory, filename), mets_filegroups[folder_with_USE])
                                physical_div.append(M.fptr({"FILEID": id}))
                            elif filename and directory.endswith('schemas'):
                                # schema files
                                id = self.addFile(os.path.join(directory, filename), mets_filegroups[folder_with_USE])
                                mets_structmap_schema_div.append(M.fptr({'FILEID': id}))
                                physical_div.append(M.fptr({'FILEID': id}))
                            elif filename:
                                try:
                                    id = self.addFile(os.path.join(directory, filename),
                                                      mets_filegroups[folder_with_USE])
                                    mets_structmap_content_div.append(M.fptr({'FILEID': id}))
                                    physical_div.append(M.fptr({'FILEID': id}))
                                except KeyError as error:
                                    logger.error("Error looking up '%s' element for file '%s'" % (folder_with_USE, filename), error)

        str = etree.tostring(root, encoding='UTF-8', pretty_print=True, xml_declaration=True)

        if not mets_file_path:
            mets_file_path = os.path.join(self.root_path, 'METS.xml')
        with open(mets_file_path, 'w') as output_file:
            output_file.write(str.decode('utf-8'))
