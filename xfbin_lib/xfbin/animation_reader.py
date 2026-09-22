"""Read animation pages without decoding unrelated meshes, textures or particles.

Each animation occurrence is a fresh object. Chunk-map identities may be reused
on later pages, but their reference aliases and payloads must not be overwritten.
"""
import struct

from .structure.br.br_xfbin import BrChunk, BrChunkTable, BrNuccHeader, BrNuccChunk
from .structure.nucc import NuccChunk
from .structure.xfbin import ChunkReference, Page, Xfbin
from .util import BinaryReader, Endian


def read_animation_xfbin(filepath):
    with open(filepath, 'rb') as stream:
        data = stream.read()
    br = BinaryReader(data, Endian.BIG, 'cp932')
    br.read_struct(BrNuccHeader)
    table = br.read_struct(BrChunkTable)
    props = [table.get_props_from_chunk_map(m) for m in table.chunkMaps]
    chunks = [NuccChunk.create_from_nucc_type(*p) for p in props]
    xfbin = Xfbin()
    start = reference_start = 0
    pending = []
    while not br.eof():
        raw = br.read_struct(BrChunk)
        prop = props[table.chunkMapIndices[start + raw.chunkMapIndex]]
        if prop[0] in ('nuccChunkAnm', 'nuccChunkCamera') and raw.size:
            pending.append((prop, BrNuccChunk.create_from_nucc_type(
                *prop, raw.data, raw.nuccId, raw.unk)))
        elif prop[0] in ('nuccChunkAnmStrm', 'nuccChunkAnmStrmFrame') and raw.size:
            raise NotImplementedError('Streaming animations are not supported: ' + prop[2])
        if prop[0] == 'nuccChunkPage':
            count, reference_count = struct.unpack('>II', raw.data[:8])
            indices = table.chunkMapIndices[start:start + count]
            page = Page()
            page.initial_page_chunks = [chunks[i] for i in indices]
            page.chunk_references = [ChunkReference(table.chunkNames[r.chunkNameIndex], chunks[r.chunkMapIndex])
                                     for r in table.chunkMapReferences[reference_start:reference_start + reference_count]]
            for prop, parsed in pending:
                chunk = NuccChunk.create_from_nucc_type(*prop)
                chunk.init_data(parsed, chunks, indices, page.chunk_references)
                page.chunks.append(chunk)
            xfbin.pages.append(page)
            pending = []
            start += count
            reference_start += reference_count
    if pending:
        raise ValueError('Incomplete animation page: missing page delimiter')
    return xfbin
