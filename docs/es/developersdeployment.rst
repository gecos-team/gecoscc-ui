Despliegue para desarrolladores
===============================


El despliegue para desarrolladores se ha probado en sistemas Linux como CentOS
6.3, OpenSuse 12.3 y Ubuntu. Esta documentación de despliegue se centrará en
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

Aconsejamos usar la última versión estable de mongodb propuesta por la empresa
que desarrolla MongoDB, 10gen.

1. Crear el fichero /etc/yum.repos.d/mongodb.repo con el siguiente contenido

  .. code-block:: ini

    [mongodb]
    name=MongoDB Repository
    baseurl=http://downloads-distro.mongodb.org/repo/redhat/os/x86_64/
    gpgcheck=0
    enabled=1

2. Instalar los siguientes paquetes

   .. code-block:: none

     mongo-10gen mongo-10gen-server


Creación del virtualenv
+++++++++++++++++++++++

Para poder crear el entorno virtualenv, es necesario instalar primero el
paquete virtualenv desde el repositorio de paquetes python pypi. Para realizar
ello ejecutar la siguiente instrucción como root

.. code-block:: none

  # easy_install virtualenv


Ahora creamos un virtualenv llamado gecoscc


.. code-block:: none

   virtualenv gecoscc


Antes de continuar, necesitamos cargar el entorno del virtualenv, para ello
ejecutamos:

.. code-block:: none

   cd gecoscc
   source bin/activate


Para verificar que el virtualenv se ha cargado correctamente, puede mirar el
prompt de su terminal y comprobar que empieza por (gecoscc).


Descarga y despliegue del proyecto
++++++++++++++++++++++++++++++++++

Para descargar el proyecto usaremos git.

.. code-block:: none

  git clone git@github.com:gecos-team/gecoscc-ui.git


Ahora procedemos a instalar todas las dependencias del código así como a
desplegar el propio paquete gecoscc-ui que acabamos de descargar.

.. code-block:: none

  cd gecoscc-ui
  python setup.py develop



Operaciones a realizar antes de arrancar el servicio
++++++++++++++++++++++++++++++++++++++++++++++++++++

Antes de arrancar los servicios de la aplicación es necesario asegurarse que
tendremos acceso a los puertos y servicios como mongodb.

Si trabajamos en local, podemos no necesitar abrir puertos extra. Sin embargo
si queremos acceder desde otro puesto a la aplicación, por ejemplo, en el caso
de la recolección de eventos de actualización de cambios realizados en los
puestos, será necesario habilitar por lo menos el puerto del servicio web.

Los comandos de firewall lokkit se encuetran disponibles en Centos, si usa
Ubuntu o Suse debería usar el software necesario en caso de tener realmente
activado un firewall.

Como root, se recomienda ejecutar los siguientes comandos:

.. code-block:: none

  # Habilitamos el servicio mongod para arranque con el sistema
  chkconfig mongod on

  # Arrancamos el servicio mongod
  service mongod start

  # abrimos el puerto para la aplicación web en modo desarrollo
  lokkit -p 6543:tcp


Arranque de servicios de desarrollo
+++++++++++++++++++++++++++++++++++

Para arrancar las aplicación es necesario arrancar tanto la aplicación web como
el worker de celery. Para arrancar ambos comandos puede usar terminales
diferentes o bien lanzar alguna de las aplicaciones modo demonio. Sin embargo,
para desarrollo recomendamos lanzar cada servicio en una terminal diferente
para tener accesible la salida de terminal o log.

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


Si está desplegando el servicio en su propio sistema, es decir, en local,
introduzca la siguiente URL en su navegador.

.. code-block:: none

  http://localhost:6543/


Para acceder al panel de control necesitará crear un usuario administrador.
Con el entorno de virtualenv cargado y desde el directorio del virtualenv,
ejecute el siguiente comando:


.. code-block:: none

  pmanage gecoscc/config-templates/development.ini createsuperuser \
        --username admin --email admin@example.com


El comando le preguntará por un password para el usuario.
