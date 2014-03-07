python setup.py extract_messages
python setup.py update_catalog

python setup.py extract_messages --output-file=gecoscc/locale/gecoscc_js.pot --mapping-file=message-extraction-js.ini
python setup.py update_catalog --input-file=gecoscc/locale/gecoscc_js.pot --domain=gecoscc_js
