// Exercise the actual DOSBox-X ZIP stream adapter and minizip implementation.
#include <iostream>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <cstring>
#include "zipcppstdbuf.h"

static void require(bool valid, const char *message) {
    if (!valid) throw std::runtime_error(message);
}

static void check(const std::string &path, int method) {
    const std::string payload = "prefix: an empty VGA buffer follows; suffix";
    zipFile file = zipOpen64(path.c_str(), APPEND_STATUS_CREATE);
    require(file != NULL, "open ZIP");
    zip_fileinfo info = {};
    require(zipOpenNewFileInZip64(file, "Vga", &info, NULL, 0, NULL, 0,
                                 NULL, method, method ? 6 : 0, 1) == ZIP_OK,
            "open ZIP entry");
    {
        zip_ostreambuf buffer(file);
        std::ostream stream(&buffer);
        stream.write(payload.data(), 7);
        // An unallocated optional native buffer has no bytes to serialize.
        // Call sputn directly too, so standard-library write optimizations do
        // not hide the adapter's zero-length behavior on another platform.
        require(buffer.sputn(NULL, 0) == 0, "null empty write");
        stream.write(payload.data() + 7, 0);
        stream.write(payload.data() + 7, payload.size() - 7);
        require(stream.good(), "stream write");
        require(buffer.close() == ZIP_OK, "close ZIP entry");
    }
    require(zipClose(file, NULL) == ZIP_OK, "close ZIP");

    unzFile saved = unzOpen64(path.c_str());
    require(saved != NULL, "open saved ZIP");
    require(unzLocateFile(saved, "Vga", 1) == UNZ_OK, "locate VGA entry");
    unz_file_info64 entry = {};
    require(unzGetCurrentFileInfo64(saved, &entry, NULL, 0, NULL, 0, NULL, 0) == UNZ_OK,
            "read ZIP metadata");
    require(entry.crc == crc32(0, reinterpret_cast<const Bytef *>(payload.data()),
                             static_cast<uInt>(payload.size())), "archive CRC changed after empty write");
    require(unzOpenCurrentFile(saved) == UNZ_OK, "open saved entry");
    char bytes[128] = {};
    const int count = unzReadCurrentFile(saved, bytes, sizeof(bytes));
    require(count == static_cast<int>(payload.size()), "restored length");
    require(std::string(bytes, count) == payload, "restored bytes");
    require(unzCloseCurrentFile(saved) == UNZ_OK, "restored CRC");
    require(unzClose(saved) == UNZ_OK, "close saved ZIP");

    if (method == 0) {
        // Change one stored payload byte without changing its CRC metadata.
        // The normal reader must still reject the resulting corruption.
        std::fstream altered(path, std::ios::in | std::ios::out | std::ios::binary);
        std::string archive((std::istreambuf_iterator<char>(altered)), {});
        const auto offset = archive.find(payload);
        require(offset != std::string::npos, "find stored payload");
        altered.clear();
        altered.seekp(offset);
        altered.put('!');
        altered.close();
        saved = unzOpen64(path.c_str());
        require(saved != NULL, "open altered ZIP");
        require(unzOpenCurrentFile(saved) == UNZ_OK, "open altered entry");
        require(unzReadCurrentFile(saved, bytes, sizeof(bytes)) == count, "read altered entry");
        require(unzCloseCurrentFile(saved) == UNZ_CRCERROR, "corruption must fail CRC validation");
        require(unzClose(saved) == UNZ_OK, "close altered ZIP");
    }
}

int main(int argc, char **argv) {
    try {
        require(argc == 2, "supply a private output directory");
        check(std::string(argv[1]) + "/stored.zip", 0);
        check(std::string(argv[1]) + "/deflated.zip", Z_DEFLATED);
        std::cout << "PASS: stored/deflated empty writes preserve bytes and CRC; corrupt payload rejected\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
