#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 Colin Walters <walters@redhat.com>
# Forked from:
# guest-image-ovf-creator.py - Copyright (C) 2013 Red Hat, Inc.
# Written by Joey Boggs <jboggs@redhat.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
# MA  02110-1301, USA.  A copy of the GNU General Public License is
# also available at http://www.gnu.org/copyleft/gpl.html.

import json
import os
import sys
import struct
import uuid
import tempfile
import logging
import hashlib
import time
import argparse
import shutil
import subprocess
import distutils.spawn
from gi.repository import Gio, OSTree, GLib
import iniparse

from .taskbase import TaskBase
from .utils import run_sync, fail_msg

OVF_VERSION = "3.3.0.0"


OVF_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!-- Generated by cloud2ovf.py from github.com/projectatomic/rpm-ostree-toolbox -->
<Envelope xmlns="http://schemas.dmtf.org/ovf/envelope/1" xmlns:cim="http://schemas.dmtf.org/wbem/wscim/1/common" xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1" xmlns:rasd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData" xmlns:vssd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <References>
    <File ovf:href="%(disk_file_name)s" ovf:id="file1" ovf:size="%(raw_disk_size)s" />
  </References>
  <DiskSection>
    <Info>Virtual disk information</Info>
    <Disk ovf:capacity="%(disk_size_gb)s" ovf:boot="true" ovf:capacityAllocationUnits="byte * 2^30" ovf:diskId="vmdisk1" ovf:fileRef="file1" ovf:format="http://www.vmware.com/interfaces/specifications/vmdk.html#streamOptimized" ovf:populatedSize="1070137344" />
  </DiskSection>
  <NetworkSection>
    <Info>The list of logical networks</Info>
    <Network ovf:name="VM Network">
      <Description>The VM Network network</Description>
    </Network>
  </NetworkSection>
  <VirtualSystem ovf:id="atomic">
    <Info>A virtual machine</Info>
    <Name>Atomic</Name>
    <OperatingSystemSection ovf:id="80" ovf:version="6">
      <Info>The kind of installed guest operating system</Info>
    </OperatingSystemSection>
    <VirtualHardwareSection>
      <Info>Virtual hardware requirements</Info>
      <System>
        <vssd:ElementName>Virtual Hardware Family</vssd:ElementName>
        <vssd:InstanceID>0</vssd:InstanceID>
        <vssd:VirtualSystemIdentifier>atomic</vssd:VirtualSystemIdentifier>
        <vssd:VirtualSystemType>vmx-08</vssd:VirtualSystemType>
      </System>
      <Item>
        <rasd:AllocationUnits>hertz * 10^6</rasd:AllocationUnits>
        <rasd:Description>Number of Virtual CPUs</rasd:Description>
        <rasd:ElementName>1 virtual CPU(s)</rasd:ElementName>
        <rasd:InstanceID>1</rasd:InstanceID>
        <rasd:ResourceType>3</rasd:ResourceType>
        <rasd:VirtualQuantity>1</rasd:VirtualQuantity>
      </Item>
      <Item>
        <rasd:AllocationUnits>byte * 2^20</rasd:AllocationUnits>
        <rasd:Description>Memory Size</rasd:Description>
        <rasd:ElementName>2048MB of memory</rasd:ElementName>
        <rasd:InstanceID>2</rasd:InstanceID>
        <rasd:ResourceType>4</rasd:ResourceType>
        <rasd:VirtualQuantity>2048</rasd:VirtualQuantity>
      </Item>
      <Item>
        <rasd:Address>1</rasd:Address>
        <rasd:Description>IDE Controller</rasd:Description>
        <rasd:ElementName>VirtualIDEController 1</rasd:ElementName>
        <rasd:InstanceID>3</rasd:InstanceID>
        <rasd:ResourceType>5</rasd:ResourceType>
      </Item>
      <Item>
        <rasd:Address>0</rasd:Address>
        <rasd:Description>IDE Controller</rasd:Description>
        <rasd:ElementName>VirtualIDEController 0</rasd:ElementName>
        <rasd:InstanceID>4</rasd:InstanceID>
        <rasd:ResourceType>5</rasd:ResourceType>
      </Item>
      <Item ovf:required="false">
        <rasd:AutomaticAllocation>false</rasd:AutomaticAllocation>
        <rasd:ElementName>VirtualVideoCard</rasd:ElementName>
        <rasd:InstanceID>5</rasd:InstanceID>
        <rasd:ResourceType>24</rasd:ResourceType>
      </Item>
      <Item ovf:required="false">
        <rasd:AutomaticAllocation>false</rasd:AutomaticAllocation>
        <rasd:ElementName>VirtualVMCIDevice</rasd:ElementName>
        <rasd:InstanceID>6</rasd:InstanceID>
        <rasd:ResourceSubType>vmware.vmci</rasd:ResourceSubType>
        <rasd:ResourceType>1</rasd:ResourceType>
      </Item>
      <Item ovf:required="false">
        <rasd:AddressOnParent>0</rasd:AddressOnParent>
        <rasd:AutomaticAllocation>false</rasd:AutomaticAllocation>
        <rasd:ElementName>CD-ROM 1</rasd:ElementName>
        <rasd:InstanceID>7</rasd:InstanceID>
        <rasd:Parent>3</rasd:Parent>
        <rasd:ResourceSubType>vmware.cdrom.remotepassthrough</rasd:ResourceSubType>
        <rasd:ResourceType>15</rasd:ResourceType>
      </Item>
      <Item>
        <rasd:AddressOnParent>0</rasd:AddressOnParent>
        <rasd:ElementName>Hard Disk 1</rasd:ElementName>
        <rasd:HostResource>ovf:/disk/vmdisk1</rasd:HostResource>
        <rasd:InstanceID>8</rasd:InstanceID>
        <rasd:Parent>4</rasd:Parent>
        <rasd:ResourceType>17</rasd:ResourceType>
      </Item>
      <Item ovf:required="false">
        <rasd:AddressOnParent>0</rasd:AddressOnParent>
        <rasd:AutomaticAllocation>false</rasd:AutomaticAllocation>
        <rasd:Description>Floppy Drive</rasd:Description>
        <rasd:ElementName>Floppy 1</rasd:ElementName>
        <rasd:InstanceID>9</rasd:InstanceID>
        <rasd:ResourceSubType>vmware.floppy.remotedevice</rasd:ResourceSubType>
        <rasd:ResourceType>14</rasd:ResourceType>
      </Item>
      <Item>
        <rasd:AddressOnParent>7</rasd:AddressOnParent>
        <rasd:AutomaticAllocation>true</rasd:AutomaticAllocation>
        <rasd:Connection>VM Network</rasd:Connection>
        <rasd:Description>VmxNet3 ethernet adapter on "VM Network"</rasd:Description>
        <rasd:ElementName>Ethernet 1</rasd:ElementName>
        <rasd:InstanceID>10</rasd:InstanceID>
        <rasd:ResourceSubType>VmxNet3</rasd:ResourceSubType>
        <rasd:ResourceType>10</rasd:ResourceType>
      </Item>
    </VirtualHardwareSection>
  </VirtualSystem>
</Envelope>
"""

class Cloud2OVF(object):
    def __init__(self, input_disk, output_ova, tmp_dir):
        self._input_disk = input_disk
        self._output = output_ova
        self._tmp_dir = tmp_dir
        
        if os.path.exists(output_ova):
            raise RuntimeError("Output path '" + output_ova + "' exists")

        self._image_basename = os.path.basename(os.path.splitext(input_disk)[0])
        self._image_name = self._image_basename + '.vmdk'
        logging.info("Image Name: %s" % self._image_basename)
        self._raw_create_time = time.time()
        self._create_time = time.gmtime(self._raw_create_time)
        self._ovf_template_dest = os.path.join(self._tmp_dir,
                                               self._image_basename + ".ovf")
        self._mf_dest = os.path.join(self._tmp_dir,
                                     self._image_basename + ".mf")
        self._disk_dest = os.path.join(self._tmp_dir, self._image_name)
        logging.info("OVF Template: %s" % self._ovf_template_dest)
        logging.info("Disk Destination: %s" % self._disk_dest)

    def _get_qcow_size(self):
        qcow_struct = ">IIQIIQIIQQIIQ"  # > means big-endian
        qcow_magic = 0x514649FB  # 'Q' 'F' 'I' 0xFB
        f = open(self._input_disk, "r")
        pack = f.read(struct.calcsize(qcow_struct))
        f.close()
        unpack = struct.unpack(qcow_struct, pack)
        if unpack[0] == qcow_magic:
            size = unpack[5]
        return size

    def _write_ovf_template(self, input_size):
        ovf_dict = {"product_name": self._image_name,
                    "ovf_version": OVF_VERSION,
                    "disk_file_name": self._image_name,
                    "snapshot_id": str(uuid.uuid4()),
                    "storage_pool_id": str(uuid.uuid4()),
                    "raw_disk_size": input_size,
                    "disk_size_gb": input_size / (1024 * 1024 * 1024),
                    "timestamp": time.strftime("%Y/%m/%d %H:%M:%S",
                                               self._create_time)
                    }
        logging.info("Writing OVF Template")
        with open(self._ovf_template_dest, "w") as f:
            f.write(OVF_TEMPLATE % ovf_dict)

    def _generate_mf(self):
        with open(self._mf_dest, 'w') as f:
            for path in [self._ovf_template_dest,
                         self._disk_dest]:
                bn = os.path.basename(path)
                s = hashlib.sha1()
                with open(path) as infile:
                    buf = infile.read(8192)
                    while buf != '':
                        s.update(buf)
                        buf = infile.read(8192)
                f.write('SHA1(%s) = %s\n'  % (bn, s.hexdigest()))

    def run(self):
        input_size = self._get_qcow_size()
        print "qcow2 size: %s" % (input_size, )
        run_sync(['qemu-img', 'convert', '-O', 'vmdk', '-f', 'qcow2', self._input_disk, self._disk_dest])
        self._write_ovf_template(input_size=input_size)
        self._generate_mf()
        run_sync(['tar', '-C', self._tmp_dir, '-c', '-f', self._output,
                  os.path.basename(self._ovf_template_dest),
                  os.path.basename(self._disk_dest),
                  os.path.basename(self._mf_dest)])

def main():
    logging.basicConfig()

    parser = argparse.ArgumentParser(description='Turn a qcow2 disk image into an OVA file')
    parser.add_argument('-i', '--input', type=str, required=True, help="Input qcow2")
    parser.add_argument('-o', '--output', type=str, required=True, help="Output destination")
    args = parser.parse_args()

    tmp_dir = tempfile.mkdtemp('cloud2ovf')
    try:
        task = Cloud2OVF(args.input, args.output, tmp_dir)
        task.run()
    finally:
        shutil.rmtree(tmp_dir)
