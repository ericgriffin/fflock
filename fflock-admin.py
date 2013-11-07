import os


os.system("python ./modules/web2py/web2py.py -s fflockadmin -i 0.0.0.0 -p 443 -P -a fflock -c ./server.crt -k ./server.key")
