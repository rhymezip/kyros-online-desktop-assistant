// A native app entry point preserves normal macOS app identity and permissions.
#include <mach-o/dyld.h>
#include <limits.h>
#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
int main(int argc, char **argv) {
    char executable[PATH_MAX], resolved[PATH_MAX];
    uint32_t size = sizeof(executable);
    if (_NSGetExecutablePath(executable, &size) || !realpath(executable, resolved)) return 1;
    // .../project/Kyros.app/Contents/MacOS/kyros -> project
    for (int i = 0; i < 4; ++i) {
        char *slash = strrchr(resolved, '/');
        if (!slash) return 1;
        *slash = '\0';
    }
    if (chdir(resolved)) { perror("Kyros project directory"); return 1; }
    char python[PATH_MAX];
    if (snprintf(python, sizeof(python), "%s/venv/bin/python", resolved) >= sizeof(python)) return 1;
    char **args = calloc((size_t)argc + 2, sizeof(char *));
    if (!args) return 1;
    args[0] = python;
    args[1] = "main.py";
    for (int i = 1; i < argc; ++i) args[i + 1] = argv[i];
    execv(python, args);
    perror("Kyros: run install.sh first");
    return 1;
}
