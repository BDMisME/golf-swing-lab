#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <libgen.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <sys/stat.h>

static int file_exists(const char *path) {
    struct stat st;
    return (stat(path, &st) == 0);
}

static int is_executable(const char *path) {
    struct stat st;
    if (stat(path, &st) != 0) return 0;
    return (st.st_mode & S_IXUSR) != 0;
}

static void show_native_alert(const char *title, const char *message) {
    char cmd[4096];
    snprintf(cmd, sizeof(cmd),
             "osascript -e 'display alert \"%s\" message \"%s\" as critical' >/dev/null 2>&1",
             title, message);
    system(cmd);
}

int main(int argc, char *argv[]) {
    // 1. 設定完整的系統 PATH 環境變數
    char env_path[2048];
    const char *existing_path = getenv("PATH");
    const char *home = getenv("HOME");
    if (!home) home = "/tmp";

    snprintf(env_path, sizeof(env_path),
             "/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:%s/.local/bin:%s/.cargo/bin:/usr/bin:/bin:/usr/sbin:/sbin:%s",
             home, home, existing_path ? existing_path : "");
    setenv("PATH", env_path, 1);
    setenv("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES", 1);

    // 2. 動態解析自身二進位執行檔的真實絕對路徑
    char exec_path[PATH_MAX];
    uint32_t size = sizeof(exec_path);
    if (_NSGetExecutablePath(exec_path, &size) != 0) {
        show_native_alert("Golf Swing Lab 啟動失敗", "無法動態解析 App 執行路徑。");
        return 1;
    }

    char resolved_exec[PATH_MAX];
    if (!realpath(exec_path, resolved_exec)) {
        strncpy(resolved_exec, exec_path, sizeof(resolved_exec) - 1);
    }

    // 3. 動態尋找專案根目錄與 desktop_app.py
    char project_dir[PATH_MAX] = {0};
    char python_bin[PATH_MAX] = {0};
    char script_path[PATH_MAX] = {0};

    // 檢查是否有外部指定的 GSL_PROJECT_DIR
    const char *custom_dir = getenv("GSL_PROJECT_DIR");
    if (custom_dir && file_exists(custom_dir)) {
        strncpy(project_dir, custom_dir, sizeof(project_dir) - 1);
    } else {
        // 優先檢查 App Bundle 內部封裝之 Resources/app
        char bundle_res_app[PATH_MAX];
        char temp_exec[PATH_MAX];
        strncpy(temp_exec, resolved_exec, sizeof(temp_exec) - 1);
        char *macos_dir = dirname(temp_exec);
        if (macos_dir) {
            char *contents_dir = dirname(macos_dir);
            if (contents_dir) {
                snprintf(bundle_res_app, sizeof(bundle_res_app), "%s/Resources/app", contents_dir);
                char check_internal[PATH_MAX];
                snprintf(check_internal, sizeof(check_internal), "%s/desktop_app.py", bundle_res_app);
                if (file_exists(check_internal)) {
                    strncpy(project_dir, bundle_res_app, sizeof(project_dir) - 1);
                }
            }
        }

        // 若 Bundle 內部無獨立封裝，從 resolved_exec 逐層向上探測 (最多向上 6 層)
        if (project_dir[0] == '\0') {
            char current_probe[PATH_MAX];
            strncpy(current_probe, resolved_exec, sizeof(current_probe) - 1);

            for (int i = 0; i < 6; i++) {
                char *pdir = dirname(current_probe);
                if (!pdir || strcmp(pdir, "/") == 0 || strcmp(pdir, ".") == 0) break;
                
                char check_script[PATH_MAX];
                snprintf(check_script, sizeof(check_script), "%s/desktop_app.py", pdir);
                if (file_exists(check_script)) {
                    strncpy(project_dir, pdir, sizeof(project_dir) - 1);
                    break;
                }
                
                // 檢查常見同級資料夾
                char check_sub[PATH_MAX];
                snprintf(check_sub, sizeof(check_sub), "%s/Golf_Swing_Lab/desktop_app.py", pdir);
                if (file_exists(check_sub)) {
                    snprintf(project_dir, sizeof(project_dir), "%s/Golf_Swing_Lab", pdir);
                    break;
                }

                strncpy(current_probe, pdir, sizeof(current_probe) - 1);
            }
        }

        // 若仍未找到，嘗試標準位置 ~/Desktop/Golf_Swing_Lab
        if (project_dir[0] == '\0') {
            char fallback_desktop[PATH_MAX];
            snprintf(fallback_desktop, sizeof(fallback_desktop), "%s/Desktop/Golf_Swing_Lab", home);
            if (file_exists(fallback_desktop)) {
                strncpy(project_dir, fallback_desktop, sizeof(project_dir) - 1);
            }
        }
    }

    if (project_dir[0] == '\0') {
        show_native_alert("Golf Swing Lab 啟動失敗",
                          "找不到 Golf Swing Lab 應用程式資料夾或 desktop_app.py。請確認應用程式已完整安裝或設定 GSL_PROJECT_DIR 環境變數。");
        return 1;
    }

    snprintf(script_path, sizeof(script_path), "%s/desktop_app.py", project_dir);

    // 4. 動態尋找可用的 Python 虛擬環境
    // 優先順序:
    // a. 專案目錄下的 .venv/bin/python
    // b. App Bundle 內部的 Resources/python/bin/python3
    // c. ~/Library/Application Support/GolfSwingLab/venv/bin/python
    // d. 系統 brew 中的 python3.12 / python3
    char venv_python[PATH_MAX];
    snprintf(venv_python, sizeof(venv_python), "%s/.venv/bin/python", project_dir);
    if (is_executable(venv_python)) {
        strncpy(python_bin, venv_python, sizeof(python_bin) - 1);
    } else {
        char app_support_python[PATH_MAX];
        snprintf(app_support_python, sizeof(app_support_python), "%s/Library/Application Support/GolfSwingLab/venv/bin/python", home);
        if (is_executable(app_support_python)) {
            strncpy(python_bin, app_support_python, sizeof(python_bin) - 1);
        } else if (is_executable("/opt/homebrew/bin/python3")) {
            strncpy(python_bin, "/opt/homebrew/bin/python3", sizeof(python_bin) - 1);
        } else if (is_executable("/usr/local/bin/python3")) {
            strncpy(python_bin, "/usr/local/bin/python3", sizeof(python_bin) - 1);
        } else {
            strncpy(python_bin, "python3", sizeof(python_bin) - 1);
        }
    }

    // 5. 切換當前工作目錄至專案目錄
    if (chdir(project_dir) != 0) {
        show_native_alert("Golf Swing Lab 啟動失敗", "無法切換工作目錄至專案路徑。");
        return 1;
    }

    // 6. 啟動桌面主程式
    char *exec_args[] = {
        python_bin,
        script_path,
        NULL
    };

    execv(python_bin, exec_args);
    show_native_alert("Golf Swing Lab 啟動失敗", "無法執行 Python 直譯器啟動桌面介面。");
    return 1;
}
