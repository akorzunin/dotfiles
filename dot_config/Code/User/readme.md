# export extensions

code --list-extensions > extensions.txt

# install from file

cat ext.txt | xargs -L 1 code --install-extension
