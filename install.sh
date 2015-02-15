#!/bin/bash


INSTALL_DIR=
PROVIDED_PREFIX=

print_usage() {
	echo -en "install.sh: Installs GoodTests.py\n\n";
	echo -en "Install Location:\n  Install location is determined by following means, in order:\n\n";
	echo -e "    1. --install-dir=DIRECTORY             Installs the program into the given directory"
	echo -e "    2. --prefix=PATH                       Installs program into \"PATH\"/bin. Ex: --prefix=/usr or --prefix=~/";
	echo -e "    3. \$PREFIX environment variable        Installs the  program into \$PREFIX/bin. Ex: PREFIX=/usr/local ./install.sh";
	echo -e "    4. If /usr/bin is writeable            Installs program into /usr/bin";
	echo -e "    5. If \$HOME is writeable               Installs program into \$HOME/bin";
	echo    "    6. Out of luck, bud.                   Prints this message.";
}

echoerr() {
	echo $@ >&2
}

strip_trailing_slash() {
	echo $@ | sed 's|/$||'
}

check_install_dir_overlap() {
	if [ ! -z "$INSTALL_DIR" -o ! -z "$PROVIDED_PREFIX" ];
	then
		echoerr -e "May only use one of --prefix or --install-dir in arguments\n\n\n";
		print_usage
		exit 1;
	fi
	return 0;
}

for arg in "$@"
do
	if [ "$arg" = "--help" ] || [ "$arg" = "-h" ] || [ "$arg" = "-?" ];
	then
		print_usage;
		exit 0;
	elif [ `expr match "$arg" "^--prefix="` -gt 0 ];
	then
		check_install_dir_overlap;
		PROVIDED_PREFIX="`echo $arg | sed 's/^--prefix=//'`"
	elif [ `expr match "$arg" "^--install-dir="` -gt 0 ];
	then
		check_install_dir_overlap;
		INSTALL_DIR="`echo $arg | sed 's/^--install-dir=//'`"
	else
		echoerr "WARNING: Unknown argument $arg\n"
	fi
done

if [ -z "$INSTALL_DIR" ];
then
	if [ -n "$PROVIDED_PREFIX" ];
	then
		PROVIDED_PREFIX="`strip_trailing_slash $PROVIDED_PREFIX`"
		if [ ! -d "$PROVIDED_PREFIX" ];
		then
			echoerr "No such file or directory: $PROVIDED_PREFIX"
			exit 1;
		fi
		INSTALL_DIR="$PROVIDED_PREFIX/bin"
	elif [ -n "$PREFIX" ];
	then
		PREFIX="`strip_trailing_slash $PREFIX`"
		if [ ! -d "$PREFIX" ];
		then
			echoerr "No such file or directory: $PREFIX"
			exit 1;
		fi
		INSTALL_DIR="$PREFIX/bin"
	elif [ -w "/usr/bin" ];
	then
		INSTALL_DIR='/usr/bin'
	elif [ -n "$HOME" ] && [ -w "$HOME" -o -w "$HOME/bin" ];
	then
		INSTALL_DIR="`strip_trailing_slash $HOME`/bin"
	else
		echoerr "Cannot find any place to install. Please provide a directory:\n\n"
		print_usage;
		exit 1;
	fi
fi

if [ ! -d "$INSTALL_DIR" ];
then
	INSTALL_DIR_PARENT="`dirname $INSTALL_DIR`"
	if [ -w "$INSTALL_DIR_PARENT" ];
	then
		echoerr "Warning, Install directory $INSTALL_DIR is not present, will create.";
		mkdir -p $INSTALL_DIR
		if [ $? -ne 0 ];
		then
			echoerr "Could not create install directory $INSTALL_DIR . Please check and try again.";
			exit 1;
		fi
	else
		echoerr "Could not install to directory $INSTALL_DIR . Check permissions and try again.";
		exit 1;
	fi
fi
if [ ! -w "$INSTALL_DIR" ];
then
	echoerr "Could not install to directory $INSTALL_DIR . Check permissions and try again.";
	exit 1;
fi


PACKAGE_DIRECTORY=`dirname ${BASH_SOURCE[0]}`;

echo -e "[I]\tGoodTests.py\t\t--->\t$INSTALL_DIR/GoodTests.py"
install -m 775 $PACKAGE_DIRECTORY/GoodTests.py $INSTALL_DIR/
if [ $? -ne 0 ];
then
	echoerr 'Failed to install';
	exit 1;
fi

# vim: ts=4 sw=4 noexpandtab
