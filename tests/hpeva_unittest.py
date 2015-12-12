__author__ = 'Laurynas Kavaliauskas'
import unittest
# Script DB is used to store/load the cloned lun
# information and the credentials
sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/' + '..'))
from src.libs.hpeva import SteelFusionHandoff

class TestSteelFusionHandoffPy(unittest.TestCase):

    def setUp(self):
        #This is a good place to run setup_db.py to setup your test env credentials
        pass

    def test_ok(self):
        #Setting cli argument variables
        arg_ind = sys.argv.index("--array-model")
        nbin = sys.argv[arg_ind+1]
        sys.argv.remove(nbin)
        '''
        Working array should always return 'OK'
        '''
        self.assertEqual(
                SteelFusionHandoff.main(),
                'OK')

if __name__ == '__main__':
    unittest.main()