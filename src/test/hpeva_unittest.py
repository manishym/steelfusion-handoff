__author__ = 'Laurynas Kavaliauskas'
import unittest
# Script DB is used to store/load the cloned lun
# information and the credentials
sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/' + '../..'))
from src.libs.hpeva import SteelFusionHandoff

class TestSteelFusionHandoffPy(unittest.TestCase):

    def setUp(self):
        #This is a good place to run setup_db.py to setup your test env credentials
        pass

    def test_ok(self):
        #Setting cli argument variables

        '''
        Working array should always return 'OK'
        '''
        self.assertEqual(
                SteelFusionHandoff.main(),
                '<p>this line has no special handling</p>')

    def test_ok_(self):
        '''
        incorrectly configured array should return 2
        '''
        self.assertEqual(
                run_markdown('*this should be wrapped in em tags*'),
                '<p><em>this should be wrapped in em tags</em></p>')

    def test_strong(self):
        '''
        Lines surrounded by double asterisks should be wrapped in 'strong' tags
        '''
        self.assertEqual(
                run_markdown('**this should be wrapped in strong tags**'),
                '<p><strong>this should be wrapped in strong tags</strong></p>')

if __name__ == '__main__':
    unittest.main(argv=unit_argv)