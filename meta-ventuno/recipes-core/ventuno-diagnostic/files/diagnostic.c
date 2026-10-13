#define _GNU_SOURCE
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/un.h>
#include <sys/utsname.h>
#include <time.h>
#include <unistd.h>

#ifndef APP_VERSION
#define APP_VERSION "1.0.0"
#endif
#ifndef APP_READY
#define APP_READY 1
#endif

static volatile sig_atomic_t running = 1;
static void stop(int sig) { (void)sig; running = 0; }

static int control_request(int ready)
{
    int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd < 0) return 0;
    struct timeval timeout = {.tv_sec = 2};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    strcpy(address.sun_path, "/pantavisor/pv-ctrl");
    if (connect(fd, (struct sockaddr *)&address, sizeof(address))) { close(fd); return 0; }
    const char *body = "{\"type\":\"ready\",\"payload\":\"\"}";
    char request[512], response[512] = {0};
    int size = ready
        ? snprintf(request, sizeof(request), "POST /signal HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: %zu\r\nConnection: close\r\n\r\n%s", strlen(body), body)
        : snprintf(request, sizeof(request), "GET /containers HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n");
    if (write(fd, request, size) != size) { close(fd); return 0; }
    size_t used = 0;
    while (used < sizeof(response) - 1 && !strchr(response, '\n')) {
        ssize_t n = read(fd, response + used, sizeof(response) - 1 - used);
        if (n <= 0) break;
        used += (size_t)n;
        response[used] = 0;
    }
    close(fd);
    int status = 0;
    if (sscanf(response, "HTTP/%*s %d", &status) != 1) return 0;
    return status;
}

int main(void)
{
    signal(SIGTERM, stop);
    signal(SIGINT, stop);
    signal(SIGPWR, stop);
    signal(SIGPIPE, SIG_IGN);
    char identity[64] = {0};
    FILE *identity_file = fopen("/data/identity", "r");
    if (identity_file) {
        if (!fgets(identity, sizeof(identity), identity_file)) return 4;
        fclose(identity_file);
    } else {
        identity_file = fopen("/proc/sys/kernel/random/uuid", "r");
        if (!identity_file || !fgets(identity, sizeof(identity), identity_file)) return 4;
        fclose(identity_file);
        identity_file = fopen("/data/identity", "wx");
        if (!identity_file) return 4;
        fputs(identity, identity_file);
        fflush(identity_file); fsync(fileno(identity_file)); fclose(identity_file);
    }
    identity[strcspn(identity, "\r\n")] = 0;
    if (strlen(identity) != 36 || strspn(identity, "0123456789abcdef-") != 36) return 4;
    unsigned boots = 0;
    FILE *f = fopen("/data/boots", "r");
    if (f) { if (fscanf(f, "%u", &boots) != 1) boots = 0; fclose(f); }
    f = fopen("/data/boots", "w");
    if (!f) { perror("persistent data"); return 1; }
    fprintf(f, "%u\n", ++boots);
    fflush(f); fsync(fileno(f)); fclose(f);
    int dir = open("/data", O_DIRECTORY | O_RDONLY);
    if (dir >= 0) fsync(dir);
    struct utsname info;
    uname(&info);
    int ready = 0;
    int management_status = 0;
    while (running) {
        if (!management_status) management_status = control_request(0);
        struct timespec now;
        clock_gettime(CLOCK_MONOTONIC, &now);
        f = fopen("/data/heartbeat.tmp", "w");
        if (!f) return 2;
        fprintf(f, "{\"container\":\"diagnostic\",\"application_version\":\"%s\",\"pid\":%d,\"starts\":%u,\"kernel\":\"%s\",\"uptime\":%ld,\"management_http_status\":%d,\"identity\":\"%s\"}\n", APP_VERSION, getpid(), boots, info.release, now.tv_sec, management_status, identity);
        fflush(f); fsync(fileno(f)); fclose(f);
        if (rename("/data/heartbeat.tmp", "/data/heartbeat.json")) return 3;
        if (dir >= 0) fsync(dir);
        if (!ready && APP_READY) {
            int status = control_request(1);
            ready = status == 200 || status == 204;
        }
        printf("diagnostic: pid=%d starts=%u ready=%d\n", getpid(), boots, ready);
        fflush(stdout);
        sleep(2);
    }
    if (dir >= 0) close(dir);
    return 0;
}
