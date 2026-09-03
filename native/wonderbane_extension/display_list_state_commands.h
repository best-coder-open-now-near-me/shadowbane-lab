#pragma once

// Client imports whose recorded state/geometry cannot be reconstructed by the
// feature-edge capture. Keep signatures, hook installation and rollback together.
// Texture coordinates/normals alone do not change geometric edge ownership;
// alpha-tested edges still require captured, unambiguous endpoint UVs.
#define WB_LIST_STATE_COMMANDS(X) \
    X(AlphaFunc, (unsigned int function, float reference), (function, reference)) \
    X(BindTexture, (unsigned int target, unsigned int texture), (target, texture)) \
    X(TexEnvf, (unsigned int target, unsigned int name, float value), (target, name, value)) \
    X(TexEnvfv, (unsigned int target, unsigned int name, const float* values), (target, name, values)) \
    X(TexEnvi, (unsigned int target, unsigned int name, int value), (target, name, value)) \
    X(TexEnviv, (unsigned int target, unsigned int name, const int* values), (target, name, values)) \
    X(Color4f, (float r, float g, float b, float a), (r, g, b, a)) \
    X(Color4fv, (const float* values), (values)) \
    X(Color4ub, (unsigned char r, unsigned char g, unsigned char b, unsigned char a), (r, g, b, a)) \
    X(Color4ubv, (const unsigned char* values), (values)) \
    X(Color3f, (float r, float g, float b), (r, g, b)) \
    X(Color3fv, (const float* values), (values)) \
    X(Color3ub, (unsigned char r, unsigned char g, unsigned char b), (r, g, b)) \
    X(Color3ubv, (const unsigned char* values), (values)) \
    X(PushMatrix, (), ()) \
    X(PopMatrix, (), ()) \
    X(LoadIdentity, (), ()) \
    X(LoadMatrixf, (const float* values), (values)) \
    X(LoadMatrixd, (const double* values), (values)) \
    X(MultMatrixf, (const float* values), (values)) \
    X(MultMatrixd, (const double* values), (values)) \
    X(Translatef, (float x, float y, float z), (x, y, z)) \
    X(Translated, (double x, double y, double z), (x, y, z)) \
    X(Scalef, (float x, float y, float z), (x, y, z)) \
    X(Scaled, (double x, double y, double z), (x, y, z)) \
    X(Rotatef, (float angle, float x, float y, float z), (angle, x, y, z)) \
    X(Rotated, (double angle, double x, double y, double z), (angle, x, y, z)) \
    X(Ortho, (double l, double r, double b, double t, double n, double f), (l, r, b, t, n, f)) \
    X(Frustum, (double l, double r, double b, double t, double n, double f), (l, r, b, t, n, f)) \
    X(ClipPlane, (unsigned int plane, const double* equation), (plane, equation)) \
    X(Vertex3fv, (const float* values), (values)) \
    X(Vertex2f, (float x, float y), (x, y)) \
    X(Vertex2fv, (const float* values), (values)) \
    X(Vertex4f, (float x, float y, float z, float w), (x, y, z, w)) \
    X(Vertex4fv, (const float* values), (values))
