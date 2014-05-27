Despliegue para desarrolladores
===============================


El despliegue para desarrolladores se ha probado en sistemas Linux como CentOS
6.3, OpenSuse 13.1 y Ubuntu. Esta documentación de despliegue se centrará en
entornos CentOS.


Paquetes de sistema
+++++++++++++++++++

Se necesitan los siguientes paquetes de sistema:

.. code-block:: none

   python-setuptools python-devel autoconf make gcc gettext git


Repositorios y paquetes extra
+++++++++++++++++++++++++++++

MongoDB
-------

Aconsejamos usar la última versión estable de MongoDB proporcionada por la
empresa que lo desarrolla, 10gen.

1. Crear el fichero /etc/yum.repos.d/mongodb.repo con el siguiente contenido:

.. code-block:: ini

   [mongodb]
   name=MongoDB Repository
   baseurl=http://downloads-distro.mongodb.org/repo/redhat/os/x86_64/
   gpgcheck=0
   enabled=1

2. Instalar los siguientes paquetes:

.. code-block:: none

   mongo-10gen mongo-10gen-server


Creación del virtualenv
+++++++++++++++++++++++

Para poder crear el entorno virtualenv, es necesario instalar primero el
paquete ``virtualenv`` desde el repositorio de paquetes python pypi. Para ello
hay que ejecutar la siguiente instrucción como **root**:

.. code-block:: none

   # easy_install virtualenv

Ahora creamos un virtualenv llamado gecoscc:

.. code-block:: none

   virtualenv gecoscc

Antes de continuar, se necesita cargar el entorno del virtualenv, para ello
hay que ejecutar:

.. code-block:: none

   cd gecoscc
   source bin/activate

Para verificar que el virtualenv se ha cargado correctamente, puede mirar el
prompt de su terminal y comprobar que empieza por (gecoscc).


Descarga y despliegue del proyecto
++++++++++++++++++++++++++++++++++

Para descargar el proyecto hay que usar git:

.. code-block:: none

   git clone git@github.com:gecos-team/gecoscc-ui.git


Ahora procederá a instalar todas las dependencias del código, así como a
desplegar el propio paquete gecoscc-ui que acaba de descargar.

.. code-block:: none

   cd gecoscc-ui
   python setup.py develop


Operaciones a realizar antes de arrancar el servicio
++++++++++++++++++++++++++++++++++++++++++++++++++++

Antes de arrancar los servicios de la aplicación es necesario asegurarse de que
se tendrá acceso a los puertos y servicios requeridos, como mongodb.

Si trabaja en local probablemente no necesitará abrir puertos extra. Sin
embargo, si quiere acceder desde otro puesto a la aplicación, por ejemplo, para
el caso de la recolección de eventos de actualización de cambios realizados en
los puestos, es necesario habilitar por lo menos el puerto del servicio web.

Los comandos de firewall ``lokkit`` se encuetran disponibles en CentOS, si usa
Ubuntu u OpenSuse deberá usar el software necesario en caso de tener realmente
activado un firewall.

Como root, se recomienda ejecutar los siguientes comandos:

.. code-block:: none

   # Habilitar el servicio mongod para que arranque con el sistema
   chkconfig mongod on

   # Arrancar el servicio mongod
   service mongod start

   # Abrir el puerto para la aplicación web en modo desarrollo
   lokkit -p 6543:tcp


Arranque de servicios de desarrollo
+++++++++++++++++++++++++++++++++++

Para arrancarlo es necesario arrancar tanto la aplicación web como el worker de
celery. Para arrancar ambos comandos se puede usar terminales diferentes, o
bien lanzar alguna de las aplicaciones en modo demonio. Sin embargo, para
desarrollo se recomienda lanzar cada servicio en una terminal diferente para
tener accesible la salida estándar o log.

Recuerde que en cada una de las terminales donde vaya a ejecutar los servicios
debe tener cargado correctamente el entorno del virtualenv.


Arranque de Celery
------------------

.. code-block:: none

   pceleryd config-templates/development.ini -E -B


Arranque de Aplicación web (pyramid)
------------------------------------

.. code-block:: none

   pserve config-templates/development.ini


Acceso a la aplicación
++++++++++++++++++++++

Si está desplegando el servicio en su propio sistema, es decir, en local, debe
introducir la siguiente URL en su navegador.

.. code-block:: none

   http://localhost:6543/


Carga de datos reales
+++++++++++++++++++++

Tras configurar en nuestro development.ini el chef.url correspondiente a
nuestro chef server y tras obtener y colocar en nuestra máquina la clave
privada de un super usuario podemos ejecutar los siguientes comandos para
tener una carga real de datos.

.. code-block:: none

    # Crear administrador en la UI y en chef server
    pmanage config-templates/development.ini create_chef_administrator -u new_admin -e new_admin@example.com -a SUPERUSER_USERNAME -k MY/PEM/PATH/chef_user.pem -n -s

    # Importar las politicas que haya en chef server (tiene parámetro p para importar una sola política)
    pmanage config-templates/development.ini import_policies -a SUPERUSER_USERNAME -k MY/PEM/PATH/chef_user.pem

    # Importar nodos chef
    pmanage config-templates/development.ini import_chef_nodes -a SUPERUSER_USERNAME -k MY/PEM/PATH/chef_user.pem




Carga de datos de prueba
++++++++++++++++++++++++

Es posible cargar un conjunto de datos de prueba en el mongo generados al azar,
para ello hay que ejecutar la siguiente orden:

.. code-block:: none

   mongo gecoscc utils/tree-generator.js

Este script, aparte de generar un conjunto de datos de prueba, añade un usuario
administrador con acceso a la aplicación. Las credenciales de dicho usuario
son (usuario / contraseña): *admin* / *admin*


Usuario administrador
+++++++++++++++++++++

Para acceder al panel de control necesitará crear un usuario administrador. Si
no ha ejecutado el script de carga de datos de prueba, entonces tendrá que
crear manualmente un usuario.

Con el entorno de virtualenv cargado y desde el directorio del virtualenv, hay
que ejecutar el siguiente comando:

.. code-block:: none

   pmanage gecoscc/config-templates/development.ini createsuperuser \
           --username admin --email admin@example.com

El comando le preguntará por un password para el nuevo usuario.
