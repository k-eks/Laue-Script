"""
Created on 15.02.2014

@author: Jens

A plugin for preparing CIFs for publication. Optimized for the
files generated by the XD package in the course of an invariom
refinement but also usefull for all purpose manipulation of
CIFs.
"""
KEY = 'cif'
OPTION_ARGUMENTS = {'write': None,
                    'include': None,
                    'load': None,
                    'exclude': ['apd.cif', 'xd_fft.cif', 'xd_lsm.cif', 'xd_geo.cif'],
                    'size': None,
                    'authors': None,
                    'temp': None,
                    'omit': None,
                    'sadabs': None,
                    'p4p': None,
                    'hkl': './xd.hkl'}

from lauescript.cryst.cif import CIF, value

cell_error = False


def run(config):
    """
    Called by the plugin manager.
    Asks the plugin manager for user input and calls
    the corresponding functions.
    """
    import os
    import glob
    from os import listdir

    global printer
    printer = config.setup()

    newest_cif_file = config.arg('load')
    if not newest_cif_file:
        newest_cif_file = max(glob.iglob('*.cif'), key=os.path.getctime).split('/')[-1]
    filelist = [f for f in listdir('.') if f.endswith('.cif')]
    printer('Using \'{}\' as main file.'.format(newest_cif_file))
    try:
        filelist.remove(newest_cif_file)
    except:
        pass
    include = config.arg('include')
    try:
        include = include.split(':')
    except:
        include = [include]
    for f in include:
        if f:
            filelist.append(f)

    exclude = config.arg('exclude')
    # try:
    #     exclude = exclude.split(':')
    # except:
    #     pass
    # if not exclude:
    #     exclude = ['apd.cif']
    try:
        for name in exclude:
            filelist.remove(name)
            printer('Excluding file: {}.'.format(name))
    except:
        pass
    main_cif = CIF(newest_cif_file)
    if not config.arg('shelx'):
        main_cif.add_value('_atom_type_scat_source', '\'Dittrich et al, (2013)\'')
    main_cif.add_value('_computing_molecular_graphics', '\'H\\"ubschle, (2011)\'')
    main_cif.add_value('_computing_publication_material', '\'L\\"ubben, (to be published)\'')
    if not config.arg('XD'):
        main_cif.add_value('_computing_structure_refinement', '\n;\nDittrich et al, (2013)\nVolkov et al, (2006)\n;\n')
        main_cif.add_value('_atom_type_scat_source', '\'Dittrich et al, (2013)\'')

    omit = ['_shelxl_version_number',
            '_refine_special_details',
            '_refine_ls_wR_factor_gt',
            '_refine_ls_hydrogen_treatment',
            '_refine_ls_shift/su_mean',
            '_shelx_res_checksum',
            '_refine_ls_restrained_S_all',
            '_geom_special_details',
            '_refine_ls_extinction_coef',
            '_shelx_res_file',
            '_reflns_special_details',
            '_shelx_space_group_comment',
            '_shelx_hkl_file',
            '_shelx_hkl_checksum',
            '_audit_creation_method']
    try:
        for toomit in config.arg('omit'):
            omit.append(toomit)
    except:
        printer('Using standard omit mask.')

    if config.arg('nohkl'):
        printer.highlight('Warning: Omitting reflection data.')
    else:
        hklpath = config.arg('hkl')
        pointer = open(hklpath, 'r')
        hkl = '\n;\n' + pointer.read() + '\n;\n'
        main_cif.add_value('_xd_hkl_file', hkl)
    printer()

    abs_file = config.arg('sadabs')
    if not abs_file:
        try:
            abs_file = max(glob.iglob('*.abs'), key=os.path.getctime).split('/')[-1]
        except:
            printer('\nNo sadabs output file found.')

    if abs_file:
        read_sadabs_file(main_cif, abs_file)

    p4p_file = config.arg('p4p')
    if not p4p_file:
        try:
            p4p_file = max(glob.iglob('*.p4p'), key=os.path.getctime).split('/')[-1]
        except:
            printer('\nNo P4P output file found.')

    if p4p_file:
        read_p4p_file(main_cif, p4p_file)

    add_crystal_dimensions(main_cif, config)
    if not config.arg('nodetails'):
        add_details(main_cif)

    authors = config.arg('authors')
    if authors:
        fill_authors(main_cif, authors)

    Temp = config.arg('temp')
    if Temp:
        main_cif.add_value('_cell_measurement_temperature', Temp + '(2)')
        main_cif.add_value('_diffrn_ambient_temperature', Temp + '(2)')

    printer.spacer()
    printer()
    for filename in filelist:
        new, new_tables = main_cif.complete(CIF(filename), omit=omit)
        printer('Adding data from file {}:'.format(filename))
        for v in new:
            if not len(main_cif[v]) < 200:
                p = '\n...\n...'
            else:
                p = main_cif[v]
            printer('    {:<60} {:>}'.format(v, p.replace('\n', '\n         ')))
        printer()
        for table in new_tables:
            printer('    loop_')
            for v in table:
                printer('        {}'.format(v))
        printer()
    printer.spacer()
    printer()
    if not config.arg('noxd') and not config.arg('nofix'):
        fix_esds(main_cif)
        del_angles(main_cif)
        del_table(main_cif)
    output_name = config.arg('write')
    if not output_name:
        output_name = 'apd.cif'
    printer('\nWriting CIF to disk: {}'.format(output_name))
    main_cif.write(output_name)
    printer()
    if cell_error:
        printer.highlight(' Warning: Cell parameters from CIF and P4P-file do not match.', char='//\\\\')


def fix_esds(cif):
    """
    Removes the standard uncertenties from all contrained
    bond distances as defined in an xd.mas file.
    """

    try:
        printer('\nFixing Invariom related errors in XD-CIF.')
        maspointer = open('xd.mas', 'r')
        atomlist = parse_atomlist(maspointer)
        maspointer.close()
        maspointer = open('xd.mas', 'r')
        conlist = []
        for line in maspointer.readlines():
            if line.startswith('CON'):
                atoms = []
                for block in [i for i in line.rstrip('\n').split(' ') if len(i) > 0]:
                    if '/' in block and block[0] in ('X', 'Y', 'Z'):
                        atoms.append(int(block.partition('/')[2]))
                if not atoms in conlist and len(atoms) == 2:
                    conlist.append(atoms)
        for i, con in enumerate(conlist):
            conlist[i] = (atomlist[con[0] - 1], atomlist[con[1] - 1])

        for row_keys in conlist:
            row_hkey = [i for i in row_keys if 'H(' in i]
            cif.change_value('no_esd', '_geom_bond_distance', row_keys)
            cif.change_value('no_esd', '_atom_site_fract_x', row_hkey)
            cif.change_value('no_esd', '_atom_site_fract_y', row_hkey)
            cif.change_value('no_esd', '_atom_site_fract_z', row_hkey)
    except:
        printer('Could not read xd.mas file.')


def parse_atomlist(maspointer):
    """
    Parses the atomlist in an xd.mas file provided as
    a filepoint 'maspointer'.
    """
    switch = False
    atomlist = []
    for line in maspointer.readlines():
        line = [i for i in line.rstrip('\n').split(' ') if len(i) > 0]
        if line[0] == 'DUM0':
            return atomlist
        elif 'ATOM' in line and 'AX1' in line:
            switch = True
            continue
        elif not switch:
            continue
        atomlist.append(line[0])


def del_angles(cif):
    """
    Removes angles defined by positions of hydrogens atoms.
    """
    removelist = []
    for i in xrange(3):
        for j, label in enumerate(cif['_geom_angle_atom_site_label_{}'.format(i + 1)]):
            if label.startswith('H('):
                if not j in removelist:
                    removelist.append(j)
    removelist = sorted(removelist, reverse=True)
    for index in removelist:
        cif.remove_row('_geom_angle', index)


def del_table(cif):
    """
    Removes tables from XD-CIF that are not needed.
    """
    cif.remove_table('_atom_rho_multipole_coeff_Pv')
    cif.remove_table('_atom_type_scat_source')
    cif.remove_table('_atom_type_scat_dispersion_imag')
    # ===========================================================================
    # cif.remove_table('_space_group_symop_id')
    #===========================================================================

    #===========================================================================
    # cif.remove_table('_space_group_symop_operation_xyz')
    #===========================================================================


def read_sadabs_file(cif, filename):
    """
    Reads sadabs output file to get information
    needed for publication.
    """
    try:
        printer('Reading sadabs output file: {}.'.format(filename))
        abspointer = open(filename, 'r')
        for line in abspointer.readlines():
            if 'Estimated minimum and maximum transmission' in line:
                values = [i for i in line.partition(':')[-1].rstrip('\n').split(' ') if len(i) > 0]
        cif.add_value('_exptl_absorpt_correction_T_min', values[0])
        cif.add_value('_exptl_absorpt_correction_T_max', values[1])
        abspointer.close()
    except:
        printer('Could not read sadabs output file: {}.'.format(filename))


def read_p4p_file(cif, filename):
    """
    Reads the Saint summary file to get information
    concerning cell parameter determination.
    """
    try:
        printer('Reading Saint summary file: {}.'.format(filename))
        p4ppointer = open(filename, 'r')
        for line in p4ppointer.readlines():
            if line.startswith('CELL '):
                cell_values = [i for i in line.rstrip('\r\n').split(' ') if len(i) > 0][1:]
            if line.startswith('SAINGL'):
                rfln_values = [i for i in line.split(' ') if len(i) > 0][1:-3]
        cif.add_value('_cell_measurement_reflns_used', rfln_values[0])
        cif.add_value('_cell_measurement_theta_min', rfln_values[1])
        cif.add_value('_cell_measurement_theta_max', rfln_values[2])
        check_cell(cif, cell_values)
    except:
        printer('Could not parse Saint summary file: {}'.format(filename))


def check_cell(cif, p4p_values):
    """
    The values of the parameters are compared to those
    in the primary CIF. If the values do not match a
    Warning is printed.
    """
    cif_values = []
    cif_values.append('{:.4f}'.format(value(cif['_cell_length_a'])))
    cif_values.append('{:.4f}'.format(value(cif['_cell_length_b'])))
    cif_values.append('{:.4f}'.format(value(cif['_cell_length_c'])))
    cif_values.append('{:.4f}'.format(value(cif['_cell_angle_alpha'])))
    cif_values.append('{:.4f}'.format(value(cif['_cell_angle_beta'])))
    cif_values.append('{:.4f}'.format(value(cif['_cell_angle_gamma'])))
    for i, par in enumerate(p4p_values[:-1]):
        if not par == cif_values[i]:
            global cell_error
            cell_error = True
            printer.highlight(' Warning: Cell parameters from CIF and P4P-file do not match.', char='//\\\\')


def fill_authors(cif, authors):
    """
    Reads author infomration from invcif_dat.py and
    puts a corresponding loop in the CIF.
    """
    import lauescript.data.invcif_dat as dat

    col1 = ['_publ_contact_author']
    col2 = ['_publ_author_adress']
    for author in authors:
        info = dat.get(author)
        col1.append(info[0])
        col2.append(info[1])
    printer('\nAdding author information:', *authors)
    cif.add_table([col1, col2])


def add_crystal_dimensions(cif, config):
    """
    Puts crystal size information as specified by
    cmdline option in the CIF.
    """
    try:
        dimensions = sorted(config.arg('size'))
        printer('\nAdding crystal dimension information.')
        cif.add_value('_exptl_crystal_size_min', dimensions[0])
        cif.add_value('_exptl_crystal_size_mid', dimensions[1])
        cif.add_value('_exptl_crystal_size_max', dimensions[2])
    except:
        pass


def add_details(cif):
    """
    Include the xd.res and xd.mas files in the CIF.
    """
    try:
        printer('Reading refinement instruction details.')
        pointer = open('xd.mas')
        mas = pointer.read()
        pointer.close()
        pointer = open('xd.res')
        res = pointer.read() + '\n;\n'
        pointer.close()
        details = '\n;\n' + mas + '\n\n' + res
        cif.add_value('_iucr_instruction_details', details)

    except:
        printer.highlight('Waring: No refinement instructions found.')







