import os

# https
os.system("python ./web2py/web2py.py -s fflockadmin -i 0.0.0.0 -p 443 -P -a fflock -c ./server.crt -k ./server.key")

#os.system("python ./web2py/web2py.py -s fflockadmin -i 0.0.0.0 -p 80 -P -a fflock")
