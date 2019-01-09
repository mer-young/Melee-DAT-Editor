windres -O coff melee-dat-editor.rc -o melee-dat-editor-rc.o
g++ -I"Include_py36" -L"../python-3.6.8-embed-amd64" melee-dat-editor.cpp -l"python36" melee-dat-editor-rc.o -mwindows -o "Melee DAT Editor.exe"
