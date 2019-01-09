/*
Launcher for the private copy of Python
*/


#include <Python.h>
#include <Windows.h>
#include <string>
#include <direct.h>
#include <vector>

// int main(int argc, char *argv[])
int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance,
                   LPSTR lpCmdLine, int nCmdShow)
{
    Py_NoSiteFlag = 1;
    Py_IgnoreEnvironmentFlag = 1;
    Py_InspectFlag = 1;
    wchar_t *program = Py_DecodeLocale(__argv[0], NULL);
    if (program == NULL) {
        EXIT_FAILURE;
    }
    Py_SetProgramName(program);

    char drive[3];
    char dir[260];
    _splitpath(_pgmptr, drive, dir, NULL, NULL);
    std::string launcher_dir, pypath, pyhome, path;
    launcher_dir = (std::string)drive + (std::string)dir;
    pyhome = launcher_dir + "python-3.6.8-embed-amd64/";
    pypath = pyhome + ";"
           + pyhome + "python36.zip;"
           + pyhome + "win32;"
           // + pyhome + "pywin32_system32"
           + pyhome + "pyqt5;"
           + pyhome + "pyqt5/bin;"
           + pyhome + "yaml;"
           + launcher_dir + "melee-dat-editor;";

    Py_SetPythonHome(Py_DecodeLocale(pyhome.c_str(), NULL));
    Py_SetPath(Py_DecodeLocale(pypath.c_str(), NULL));

    Py_Initialize();

    // set up PATH to find Qt DLLs etc
    std::string envstr = "import os;os.environ['PATH']=r'" + pyhome + "'";
    PyRun_SimpleString(envstr.c_str());
    
    // send args to python (allow opening a file from command line,
    // drag and drop onto icon, registering a file type, etc)
    std::vector<wchar_t*> py_argv(__argc);
    for (int i=0; i<__argc; i++){
        py_argv[i] = Py_DecodeLocale(__argv[i], NULL);
    }
    PySys_SetArgv(__argc, &py_argv[0]);
    
    _chdir("melee-dat-editor");  // let cwd be the script directory
    std::string fname = "melee_dat_editor.py";
    FILE* f = _Py_fopen(fname.c_str(), "r");
    PyRun_SimpleFileEx(f, fname.c_str(), true);
    if(Py_FinalizeEx() < 0) {
        exit(120);
    }
    PyMem_RawFree(program);
    EXIT_SUCCESS;
}
