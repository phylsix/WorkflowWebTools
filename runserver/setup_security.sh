#!/bin/bash

# Valid options for generating passwords are:
#  -aes128
#  -aes192
#  -aes256

passwordopt=$1

if [ ! -d keys ]
then
    mkdir keys
fi

if [ ! -f keys/privkey.pem ]
then
    openssl genrsa $passwordopt -out keys/privkey.pem 2048
fi

if [ ! -f keys/salt.txt ]
then
    python -mgeneratesalt > keys/salt.txt
fi

if [ ! -f keys/config.yml ]
then
    cp ../docs/config.yml keys/.
fi

openssl req -new -x509 -days 365 -key keys/privkey.pem -out keys/cert.pem

echo "Do not forget to edit the configuration file:"
echo ""
echo " keys/config.yml"
echo ""
