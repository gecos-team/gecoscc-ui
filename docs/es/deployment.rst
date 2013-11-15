Despliegue para entorno de producción básico
============================================

En este documento de despliegue se describe el método de depliegue de Gecos CC
UI usando el sistema de gestión de configuraciónes Chef de Opscode. Se ha
desarrollado un libro de recetas o cookbook para para facilitar este
despliegue.

El método que se documenta se corresponde con *chef solo* en la que no
interviene un chef-server.

Esta documentación contempla dos sistemas, el cliente y el servidor. El cliente
será la máquina donde trabajaremos. El servidor es sistema donde acabará
instalada la aplicación.


Preparar el entorno del cliente chef
++++++++++++++++++++++++++++++++++++

Existen diferentes guías de despliegue de un entorno Chef para estación de
trabajo. A continuación documentamos el proceso que usamos en Centos 6.

Instalamos el repositorio rpm rbel6 e instalamos los paquetes que vamos a
necesitar. El siguiente bloque se debe ejecutar como root. Cambia el bloque
TuUsuario por el usuario que usas en el sistema normalmente.

.. code-block:: bash

  rpm -Uvh http://rbel.frameos.org/rbel6
  yum install ruby ruby-devel ruby-ri ruby-rdoc ruby-shadow gcc gcc-c++ \
    automake autoconf make curl dmidecode git
  curl -L https://get.rvm.io | bash
  usermod -G rvm -a TuUsuario
  source /etc/profile.d/rvm.sh
  rvm install ruby-1.9.3-p448
  gem-ruby-1.9.3-p448 install bundle


Para que se apliquen los cambios de grupo realizados sería conveniente que
volvieras a iniciar sesión. Tras reiniciar sesión, ejecuta la siguiente línea
con tu usuario habitual.

.. code-block:: bash

  echo "source /etc/profile.d/rvm.sh" >> ~/.bash_profile


Una vez terminado, puedes forzar la aplicación de los cambios ejecutando la
siguiente línea:

.. code-block:: bash

  source ~/.bash_profile


Ahora creamos la carpeta de trabajo. Necesitamos un fichero .ruby-version. Una
vez tengamos el fichero en el directorio, tenemos que volver a acceder al
directorio. Podemos hacer todo esto con los siguientes comandos:


.. code-block:: bash

  mkdir gecoscc
  echo 1.9.3 > gecoscc/.ruby_version
  cd gecoscc


Ahora creamos un fichero Gemfile con el siguiente contenido:

.. code-block:: none

   gem 'knife-solo'
   gem 'librarian-chef'


Ahora ejecutamos el comando bundle para que lea el fichero Gemfile e instale
las dependencias. Este comando puede tardar varios minutos en ejecutarse porque
tiene que descargarse una gran cantidad de gemas de ruby.

.. code-block:: bash

   bundle


Ahora inicializamos el directorio como directorio de trabajo de knife.

.. code-block:: bash

   knife solo init .


Ahora creamos el fichero Cheffile donde incorporamos las recetas chef que
necesitamos. El contenido Cheffile debe tener el siguiente contenido:

.. code-block:: ruby

  site 'http://community.opscode.com/api/v1'

  cookbook 'gecosccui',
    :git => 'https://github.com/gecos-team/cookbook-gecosccui'


Ahora ejecutamos librarian-chef para que descargue los paquetes indicados en el
Cheffile y sus dependencias.

.. code-block:: bash

  librarian-chef install


Ya podemos empezar a preparar el despliegue en el servidor. Hacemos el
bootstrap de chef solo en el servidor.

.. code-block:: bash

  knife solo prepare root@server


Ahora tenemos que añadir la receta al runlist del servidor. Para esto, editamos
el fichero *nodes/root@server* Y para que se instale el panel de control web de
Gecos debe tener un aspecto como el siguiente:

.. code-block:: javascript

  {
    "run_list": [
        "recipe[gecosccui::backend]"
    ]
  }


Una vez tengamos preparada la run_list del equipo podemos ejecutar tal
run_list. Para eso podemos ejecutar el siguiente comando:

.. code-block:: bash

  knife solo cook root@server


