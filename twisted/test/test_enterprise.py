# Twisted, the Framework of Your Internet
# Copyright (C) 2001-2002 Matthew W. Lefkowitz
# 
# This library is free software; you can redistribute it and/or
# modify it under the terms of version 2.1 of the GNU Lesser General Public
# License as published by the Free Software Foundation.
# 
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
# 
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
# 
from pyunit import unittest

import os

from twisted.enterprise.row import RowObject
from twisted.enterprise.xmlreflector import XMLReflector

tableName = "testTable"

class TestRow(RowObject):

    rowColumns    = ["key_string", "col2", "another_column", "Column4", "column_5_"]
    rowKeyColumns = [("key_string", "varchar")]
    rowTableName  = tableName

class EnterpriseTestCase(unittest.TestCase):
    """Enterprise test cases. These will only work with the XML reflector for now. real database
    access requires there to be a database  :) and asynchronous tests (which these are not).
    """

    DB = "./xmlDB"
    
    def setUp(self):
        # creates XML db in file system
        self.reflector = XMLReflector(EnterpriseTestCase.DB, [TestRow])
        self.reflector._really_populate()

        # create one row to work with
        self.newRow = TestRow()
        self.newRow.assignKeyAttr("key_string", "first")
        self.newRow.col2 = 1
        self.newRow.another_column = "another"
        self.newRow.Column4 = "foo"
        self.newRow.column_5_ = 444
        self.data = None
        self.reflector.insertRow(self.newRow)        
        
    def tearDown(self):
        # cleans up the XML db from the file system
        self.reflector.deleteRow(self.newRow)        
        os.rmdir(self.DB + "/" + tableName)
    
    def testQuery(self):
        self.reflector.insertRow(self.newRow)
        self.reflector.loadObjectsFrom(tableName).addCallback(self.gotData)
        assert len(self.data) == 1, "no rows on query"
        
    def testUpdate(self):
        self.reflector.insertRow(self.newRow)
        self.reflector.updateRow(self.newRow)

    def testBulk(self):
        rows = []
        num = 40
        for i in range(0,num):
            newRow = TestRow()
            newRow.assignKeyAttr("key_string", "bulk%d"%i)
            newRow.col2 = 4
            newRow.another_column = "another"
            newRow.Column4 = "444"
            newRow.column_5_ = 1
            rows.append(newRow)
            self.reflector.insertRow(newRow)

        self.reflector.loadObjectsFrom("testTable").addCallback(self.gotData)

        assert len(self.data) == num+1, "query didnt get rows"
        
        for row in rows:
            self.reflector.updateRow(row)

        for row in rows:
            self.reflector.deleteRow(row)

    def gotData(self, data):
        self.data = data
    


    

