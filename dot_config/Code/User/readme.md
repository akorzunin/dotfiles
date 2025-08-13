# export extensions

code --list-extensions > ext.txt

# install from file

cat ext.txt | xargs -L 1 code --install-extension
