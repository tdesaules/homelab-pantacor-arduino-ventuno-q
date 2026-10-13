# Preserve sstate preprocessing/relocation, but do not retain compressed cache
# archives on the small hosted runner. SSTATE_SKIP_CREATION skips those hooks
# too and breaks native sysroot relocation in Scarthgap.
SSTATEPOSTCREATEFUNCS:append = " ventuno_ci_discard_sstate"

python ventuno_ci_discard_sstate() {
    import os
    archive = d.getVar('SSTATE_PKG')
    for path in (archive, archive + '.sig'):
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
}
