
import sys, os


sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from dags.common_utils.runtime_variable import runtime_variable

if __name__ == '__main__':
    print(__file__)
    print(sys.path[0])
    print(runtime_variable())