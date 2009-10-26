#include <string.h>
#include "ddf_outputstream.h"

DDFOutputStream::DDFOutputStream(DDFSaveFunction save_function, void* context)
{
    m_SaveFunction = save_function;
    m_Context = context;
}

bool DDFOutputStream::Write(const void* buffer, int length)
{
    return m_SaveFunction(m_Context, buffer, length);
}

bool DDFOutputStream::WriteTag(uint32_t number, DDFWireType type)
{
    uint32_t tag = number << 3;
    tag |= type;
    return WriteVarInt32(tag);
}

bool DDFOutputStream::WriteVarInt32SignExtended(int32_t value)
{
    if (value < 0)
        return WriteVarInt64((uint64_t) value);
    else
        return WriteVarInt32((uint32_t) value);
}

bool DDFOutputStream::WriteVarInt32(uint32_t value)
{
    uint8_t bytes[5];
    int size = 0;
    while (value > 0x7F)
    {
        bytes[size++] = (uint8_t(value) & 0x7F) | 0x80;
        value >>= 7;
    }
    bytes[size++] = uint8_t(value) & 0x7F;
    return Write(bytes, size);
}

bool DDFOutputStream::WriteVarInt64(uint64_t value)
{
    uint8_t bytes[10];
    int size = 0;
    while (value > 0x7F)
    {
        bytes[size++] = (uint8_t(value) & 0x7F) | 0x80;
        value >>= 7;
    }
    bytes[size++] = uint8_t(value) & 0x7F;
    return Write(bytes, size);
}

bool DDFOutputStream::WriteFixed32(uint32_t value)
{
    uint8_t buf[4];
    buf[0] = (value >> 0) & 0xff;
    buf[1] = (value >> 8) & 0xff;
    buf[2] = (value >> 16) & 0xff;
    buf[3] = (value >> 24) & 0xff;
    return Write(buf, sizeof(buf));
}

bool DDFOutputStream::WriteFixed64(uint64_t value)
{
    uint8_t buf[8];
    buf[0] = (value >> 0) & 0xff;
    buf[1] = (value >> 8) & 0xff;
    buf[2] = (value >> 16) & 0xff;
    buf[3] = (value >> 24) & 0xff;
    buf[4] = (value >> 32) & 0xff;
    buf[5] = (value >> 40) & 0xff;
    buf[6] = (value >> 48) & 0xff;
    buf[7] = (value >> 56) & 0xff;
    return Write(buf, sizeof(buf));
}

bool DDFOutputStream::WriteFloat(float value)
{
    union
    {
        float    v;
        uint32_t i;
    };
    v = value;
    return WriteFixed32(i);
}

bool DDFOutputStream::WriteDouble(double value)
{
    union
    {
        double   v;
        uint64_t i;
    };
    v = value;
    return WriteFixed64(i);
}

bool DDFOutputStream::WriteInt32(int32_t value)
{
//    return WriteVarint32SignExtended(value);
    // TODO: Fix this to signextended!!!
    return WriteVarInt32(value);
}

bool DDFOutputStream::WriteUInt32(uint32_t value)
{
    return WriteVarInt32(value);
}

bool DDFOutputStream::WriteInt64(int64_t value)
{
    return WriteVarInt64(value);
}

bool DDFOutputStream::WriteUInt64(uint64_t value)
{
    return WriteVarInt64(value);
}

bool DDFOutputStream::WriteString(const char* str)
{
    uint32_t len = strlen(str);
    return WriteVarInt32(len) && Write(str, len);
}



