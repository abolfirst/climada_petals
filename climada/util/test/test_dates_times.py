"""
This file is part of CLIMADA.

Copyright (C) 2017 CLIMADA contributors listed in AUTHORS.

CLIMADA is free software: you can redistribute it and/or modify it under the
terms of the GNU Lesser General Public License as published by the Free
Software Foundation, version 3.

CLIMADA is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along
with CLIMADA. If not, see <https://www.gnu.org/licenses/>.

---

Test of dates_times module
"""
import datetime as dt
import unittest
import numpy as np

import climada.util.dates_times as u_dt

class TestDateString(unittest.TestCase):
    """Test date functions """
    def test_date_to_str_pass(self):
        """ Test _date_to_str function"""
        ordinal_date = dt.datetime.toordinal(dt.datetime(2018, 4, 6))
        self.assertEqual('2018-04-06', u_dt.date_to_str(ordinal_date))

    def test_str_to_date_pass(self):
        """ Test _date_to_str function"""
        date = 730000
        self.assertEqual(u_dt.str_to_date(u_dt.date_to_str(date)), date)
        
class TestDateNumpy(unittest.TestCase):
    """"Test date functions for numpy datetime64 type"""
    def test_datetime64_to_ordinal(self):
        """Test _datetime64_to_ordinal"""
        date = np.datetime64('1999-12-26T06:00:00.000000000')
        ordinal = u_dt.datetime64_to_ordinal(date)
        self.assertEqual(u_dt.date_to_str(ordinal), '1999-12-26')

# Execute Tests
TESTS = unittest.TestLoader().loadTestsFromTestCase(TestDateString)
TESTS.addTests(unittest.TestLoader().loadTestsFromTestCase(TestDateNumpy))
unittest.TextTestRunner(verbosity=2).run(TESTS)
