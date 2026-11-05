"""Helpers to add OpenType feature code to a font without discarding its existing GSUB.

feaLib builds a GSUB table from scratch, so we compile the feature code against a throwaway
copy of the font and then splice the resulting lookups/features into the real GSUB.
"""
import copy
import io

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot


def _scratch_copy(font: TTFont) -> TTFont:
    """A minimal font with the same glyph order that feaLib can compile against."""
    buf = io.BytesIO()
    font.save(buf)
    buf.seek(0)
    scratch = TTFont(buf)
    if "GSUB" in scratch:
        del scratch["GSUB"]
    return scratch


def _remap_lookup_indices(lookup, offset: int) -> None:
    """Shift nested lookup references (SubstLookupRecord) by `offset`."""
    for st in lookup.SubTable:
        st = getattr(st, "ExtSubTable", st)
        for rec in getattr(st, "SubstLookupRecord", None) or []:
            rec.LookupListIndex += offset
        for attr in ("ChainSubRuleSet", "ChainSubClassSet", "SubRuleSet", "SubClassSet"):
            for ruleset in getattr(st, attr, None) or []:
                if ruleset is None:
                    continue
                rules = (getattr(ruleset, "ChainSubRule", None) or getattr(ruleset, "ChainSubClassRule", None)
                         or getattr(ruleset, "SubRule", None) or getattr(ruleset, "SubClassRule", None) or [])
                for rule in rules:
                    for rec in rule.SubstLookupRecord:
                        rec.LookupListIndex += offset


def _empty_gsub() -> ot.GSUB:
    gsub = ot.GSUB()
    gsub.Version = 0x00010000
    gsub.ScriptList = ot.ScriptList(); gsub.ScriptList.ScriptRecord = []
    gsub.FeatureList = ot.FeatureList(); gsub.FeatureList.FeatureRecord = []
    gsub.LookupList = ot.LookupList(); gsub.LookupList.Lookup = []
    return gsub


def add_features(font: TTFont, fea: str) -> None:
    """Compile `fea` (GSUB only) and append its lookups/features to `font`'s GSUB.

    Every new feature is registered in every existing script/language system of the font
    (and in DFLT/latn if those are missing), so it is active regardless of script detection.
    """
    scratch = _scratch_copy(font)
    addOpenTypeFeaturesFromString(scratch, fea, tables=["GSUB", "name"])
    donor = scratch["GSUB"].table

    if "GSUB" not in font:
        from fontTools.ttLib import newTable
        font["GSUB"] = newTable("GSUB")
        font["GSUB"].table = _empty_gsub()
    gsub = font["GSUB"].table

    offset = len(gsub.LookupList.Lookup)
    for lookup in donor.LookupList.Lookup:
        lookup = copy.deepcopy(lookup)
        _remap_lookup_indices(lookup, offset)
        gsub.LookupList.Lookup.append(lookup)
    gsub.LookupList.LookupCount = len(gsub.LookupList.Lookup)

    # feaLib stores UI names (e.g. stylistic set names) in the name table; carry new records over.
    known = {(r.nameID, r.platformID, r.platEncID, r.langID) for r in font["name"].names}
    for r in scratch["name"].names:
        if (r.nameID, r.platformID, r.platEncID, r.langID) not in known:
            font["name"].names.append(r)

    # Collect donor features by tag (feaLib emits one FeatureRecord per tag per langsys; merge them).
    donor_features: dict[str, list[int]] = {}
    donor_params: dict[str, object] = {}
    for rec in donor.FeatureList.FeatureRecord:
        donor_params.setdefault(rec.FeatureTag, rec.Feature.FeatureParams)
        idx = donor_features.setdefault(rec.FeatureTag, [])
        for li in rec.Feature.LookupListIndex:
            if li + offset not in idx:
                idx.append(li + offset)

    # Make sure DFLT and latn exist so the new features are reachable.
    existing_scripts = {sr.ScriptTag for sr in gsub.ScriptList.ScriptRecord}
    for tag in ("DFLT", "latn"):
        if tag not in existing_scripts:
            sr = ot.ScriptRecord(); sr.ScriptTag = tag
            sr.Script = ot.Script(); sr.Script.LangSysRecord = []; sr.Script.LangSysCount = 0
            sr.Script.DefaultLangSys = ot.LangSys()
            sr.Script.DefaultLangSys.ReqFeatureIndex = 0xFFFF
            sr.Script.DefaultLangSys.FeatureIndex = []
            gsub.ScriptList.ScriptRecord.append(sr)
    gsub.ScriptList.ScriptRecord.sort(key=lambda sr: sr.ScriptTag)
    gsub.ScriptList.ScriptCount = len(gsub.ScriptList.ScriptRecord)

    langsystems = []
    for sr in gsub.ScriptList.ScriptRecord:
        if sr.Script.DefaultLangSys is not None:
            langsystems.append(sr.Script.DefaultLangSys)
        langsystems.extend(lsr.LangSys for lsr in sr.Script.LangSysRecord)

    # Append one FeatureRecord per (tag, langsys) — or extend an existing record with the same tag.
    records = gsub.FeatureList.FeatureRecord
    for tag, lookup_indices in donor_features.items():
        for ls in langsystems:
            existing = [i for i in ls.FeatureIndex if records[i].FeatureTag == tag]
            if existing:
                for i in existing:
                    records[i].Feature.LookupListIndex.extend(lookup_indices)
                    records[i].Feature.LookupCount = len(records[i].Feature.LookupListIndex)
                continue
            rec = ot.FeatureRecord(); rec.FeatureTag = tag
            rec.Feature = ot.Feature(); rec.Feature.FeatureParams = copy.deepcopy(donor_params[tag])
            rec.Feature.LookupListIndex = list(lookup_indices); rec.Feature.LookupCount = len(lookup_indices)
            records.append(rec)
            ls.FeatureIndex.append(len(records) - 1)

    # The spec requires FeatureList sorted by tag; re-sort and remap LangSys feature indices.
    order = sorted(range(len(records)), key=lambda i: records[i].FeatureTag)
    new_index = {old: new for new, old in enumerate(order)}
    gsub.FeatureList.FeatureRecord = [records[i] for i in order]
    gsub.FeatureList.FeatureCount = len(records)
    for ls in langsystems:
        ls.FeatureIndex = sorted(new_index[i] for i in ls.FeatureIndex)
        ls.FeatureCount = len(ls.FeatureIndex)
        if ls.ReqFeatureIndex != 0xFFFF:
            ls.ReqFeatureIndex = new_index[ls.ReqFeatureIndex]
