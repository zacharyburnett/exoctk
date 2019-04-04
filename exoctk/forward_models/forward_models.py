"""Module to hold our forward models that until now have been floating in the
web application. 

Right now this includes database interaction and model rescaling software. 


Authors
-------
Jules Fowler, April 2019
Natasha Batalha
Hannah Wakeford


Use
---

...
"""

## -- IMPORTS


## -- FUNCTIONS

def _param_fort_validation(args):
    """Validates the input parameters for the forward models"""

    temp = args.get('ptemp', 1000)
    chem = args.get('pchem', 'noTiO')
    cloud = args.get('cloud', '0')
    pmass = args.get('pmass', '1.5')
    m_unit = args.get('m_unit', 'M_jup')
    reference_radius = args.get('refrad', 1)
    r_unit = args.get('r_unit', 'R_jup')
    rstar = args.get('rstar', 1)
    rstar_unit = args.get('rstar_unit', 'R_sun')

    return temp, chem, cloud, pmass, m_unit, reference_radius, r_unit, rstar, rstar_unit


def fortney_grid(args

    FORTGRID_DIR = os.path.join(EXOCTK_DATA, 'fortney/fortney_models.db')

    temp, chem, cloud, pmass, m_unit, reference_radius, r_unit, rstar, rstar_unit = _param_fort_validation(args)

    # get sqlite database
    try:
        db = create_engine('sqlite:///' + FORTGRID_DIR)
        header = pd.read_sql_table('header', db)
    except:
        raise Exception('Fortney Grid File Path is incorrect, or not initialized')

    if args:
        rstar = float(rstar)
        rstar = (rstar * u.Unit(rstar_unit)).to(u.km)
        reference_radius = float(reference_radius)
        rplan = (reference_radius * u.Unit(r_unit)).to(u.km)

        # clouds
        if cloud.find('flat') != -1:
            flat = int(cloud[4:])
            ray = 0
        elif cloud.find('ray') != -1:
            ray = int(cloud[3:])
            flat = 0
        elif int(cloud) == 0:
            flat = 0
            ray = 0
        else:
            flat = 0
            ray = 0
            print('No cloud parameter not specified, default no clouds added')

        # chemistry
        if chem == 'noTiO':
            noTiO = True
        if chem == 'eqchem':
            noTiO = False
            # grid does not allow clouds for cases with TiO
            flat = 0
            ray = 0

        fort_grav = 25.0 * u.m / u.s**2

        temp = float(temp)
        df = header.loc[(header.gravity == fort_grav) & (header.temp == temp) &
                        (header.noTiO == noTiO) & (header.ray == ray) &
                        (header.flat == flat)]

        wave_planet = np.array(pd.read_sql_table(df['name'].values[0], db)['wavelength'])[::-1]
        r_lambda = np.array(pd.read_sql_table(df['name'].values[0], db)['radius']) * u.km

        # All fortney models have fixed 1.25 radii
        z_lambda = r_lambda - (1.25 * u.R_jup).to(u.km)

        # Scale with planetary mass
        pmass = float(pmass)
        mass = (pmass * u.Unit(m_unit)).to(u.kg)

        # Convert radius to m for gravity units
        gravity = constants.G * (mass) / (rplan.to(u.m))**2.0

        # Scale lambbda (this technically ignores the fact that scaleheight
        # is altitude dependent) therefore, it will not be valide for very
        # very low gravities
        z_lambda = z_lambda * fort_grav / gravity

        # Create new wavelength dependent R based on scaled ravity
        r_lambda = z_lambda + rplan

        # Finally compute (rp/r*)^2
        flux_planet = np.array(r_lambda**2 / rstar**2)

        x = wave_planet
        y = flux_planet[::-1]

    else:
        df = pd.read_sql_table('t1000g25_noTiO', db)
        x, y = df['wavelength'], df['radius']**2.0 / 7e5**2.0

    tab = at.Table(data=[x, y])
    fh = StringIO()
    tab.write(fh, format='ascii.no_header')
    table_string = fh.getvalue()

    fig = figure(plot_width=1100, plot_height=400)
    fig.line(x, 1e6 * (y - np.mean(y)), color='Black', line_width=0.5)
    fig.xaxis.axis_label = 'Wavelength (um)'
    fig.yaxis.axis_label = 'Rel. Transit Depth (ppm)'



def generic_grid(input_args, write_plot=False, write_table=False):
    """
    Build a plot and table from the generic grid results. 

    Parameters
    ----------
    input_args : dict
        A dictionary of the form output from the generic grid form.
        If manual input must include : 
        r_star : The radius of the star.
        r_planet : The radius of the planet.
        gravity : The gravity.
        temperature : The temperature.
        condensation : local or rainout
        metallicity 
        c_o : carbon/oxygen ratio
        haze
        cloud
    write_plot : bool, optional
        Whether to write the plot out. Defaults to False.
    write_table : bool, optional
        Whether to write the table out. Defaults to Fals.

    Returns
    -------
    plot : bokeh object
        Unsaved bokeh plot.
    table : ascii table object
        Unsaved ascii table. 
    """
    
    # Find path to the database. 
    try:
        database_path = os.path.join(os.environ('EXOCTK_DATA'), 'generic/generic_grid_db.hdf5')
    except FileNotFoundError:
        print("You need to export 'EXOCTK_DATA' for this to work.")
        raise FileNotFoundError

    # Build rescaled model
    solution, inputs, closest_match, error_message = rescale_generic_grid(args, database_path)
    
    # Build file out
    tab = at.Table(data=[solution['wv'], solution['spectra']])
    fh = StringIO()
    tab.write(fh, format='ascii.no_header')
    
    if write_table:
        tab.write('generic.dat')

    # Plot
    fig = figure(title='Rescaled Generic Grid Transmission Spectra'.upper(), plot_width=1100, plot_height=400)
    fig.x_range.start = 0.3
    fig.x_range.end = 5
    fig.line(solution['wv'], solution['spectra'], color='Black', line_width=1)
    fig.xaxis.axis_label = 'Wavelength (um)'
    fig.yaxis.axis_label = 'Transit Depth (Rp/R*)^2'
    
    if write_plot:
        save(fig)
        
    return fig, fh


def rescale_generic_grid(input_args, database_path):
    """ Pulls a model from the generic grid, rescales it, 
    and returns the model and wavelength.

    Parameters
    ----------
    input_args : dict
        A dictionary of the form output from the generic grid form.
        If manual input must include : 
        r_star : The radius of the star.
        r_planet : The radius of the planet.
        gravity : The gravity.
        temperature : The temperature.
        condensation : local or rainout
        metallicity 
        c_o : carbon/oxygen ratio
        haze
        cloud
    database_path : str
        Path to the generic grid database.
        
    Returns
    -------
    wv : np.array
        Array of wavelength bins.
    spectra : np.array
        Array of the planetary model spectrum.
    inputs : dict
        The dictionary of inputs given to the function.
    closest_match : dict
        A dictionary with the parameters/model name of the closest
        match in the grid.
    error_message : bool, str
        Either False, for no error, or a message about what went wrong.
    """
    error_message = ''
    try:   
        # Parameter validation
        # Set up some nasty tuples first
        scaling_space = [('r_star', [0.05, 10000]),
                         ('r_planet', [0.0,  10000]),
                         ('gravity', [5.0, 50]),
                         ('temperature', [400, 2600])]
        
        inputs = {} 
        # First check the scaling
        for tup in scaling_space:
            key, space = tup
            val = float(input_args[key])
            if val >= space[0] and val <= space[1]:
                inputs[key] = val
            else:
                error_message = 'One of the scaling parameters was out of range: {}.'.format(key)
                break
        
        # Map to nearest model key
        temp_range = np.arange(600, 2700, 100)
        grav_range = np.array([5, 10, 20, 50])
        sort_temp = (np.abs(inputs['temperature'] - temp_range)).argmin()
        sort_grav = (np.abs(inputs['gravity'] - grav_range)).argmin()
        model_temp = temp_range[sort_temp]
        input_args['model_temperature'] = '0{}'.format(model_temp)[-4:]
        model_grav = grav_range[sort_grav]
        input_args['model_gravity'] = '0{}'.format(model_grav)[-2:]

        # Check the model parameters
        str_temp_range = ['0400'] + ['0{}'.format(elem)[-4:] for elem in temp_range]
        model_space = [('condensation', ['local', 'rainout']), 
                       ('model_temperature', str_temp_range),
                       ('model_gravity', ['05', '10', '20', '50']),
                       ('metallicity', ['+0.0', '+1.0', '+1.7', '+2.0', '+2.3']),
                       ('c_o', ['0.35', '0.56', '0.70', '1.00']),
                       ('haze', ['0001', '0010', '0150', '1100']),
                       ('cloud', ['0.00', '0.06', '0.20','1.00'])]
        
        model_key = ''
        for tup in model_space:
            key, space = tup
            if input_args[key] in space:
                inputs[key] = input_args[key]
                model_key += '{}_'.format(inputs[key])
            else:
                error_message = 'One of the model parameters was out of range.'
                break
        model_key = model_key[:-1]
    

        # Define constants
        boltzmann = 1.380658E-16 # gm*cm^2/s^2 * Kelvin
        permitivity = 1.6726E-24 * 2.3 #g  cgs  Hydrogen + Helium Atmosphere
        optical_depth = 0.56 
        r_sun = 69580000000 # cm
        r_jupiter = 6991100000 # cm
 
        closest_match = {'model_key': model_key, 'model_gravity': model_grav,
                         'model_temperature': model_temp}
        
        with h5py.File(database_path, 'r') as f:
            # Can't use the final NaN value
            model_wv = f['/wavelength'][...][:-1]
            model_spectra = f['/spectra/{}'.format(model_key)][...][:-1]
            
        radius_ratio = np.sqrt(model_spectra) * inputs['r_planet']/inputs['r_star']
        r_star = inputs['r_star'] * r_sun
        r_planet = inputs['r_planet'] * r_jupiter
        model_grav = model_grav * 1e2
        inputs['gravity'] = inputs['gravity'] * 1e2
        
        # Start with baseline based on model parameters
        scale_height = (boltzmann * model_temp) / (permitivity * model_grav)
        r_planet_base = np.sqrt(radius_ratio) * r_sun
        altitude = r_planet_base - (np.sqrt(radius_ratio[2000])*r_sun)
        opacity = optical_depth * np.sqrt((boltzmann * model_temp * permitivity * model_grav) / \
                                          (2 * np.pi * r_planet_base)) * \
                                  np.exp(altitude / scale_height)
        # Now rescale from baseline
        solution = {}
        solution['scale_height'] = (boltzmann * inputs['temperature']) / (permitivity * inputs['gravity'])
        solution['altitude'] = solution['scale_height'] * \
                               np.log10(opacity/optical_depth * \
                                        np.sqrt((2 * np.pi * r_planet) / \
                                                (boltzmann * inputs['temperature'] * inputs['gravity']))) 
        solution['radius'] = solution['altitude'] + r_planet

        # Sort data
        sort = np.argsort(model_wv)
        solution['wv'] = model_wv[sort]
        solution['radius'] = solution['radius'][sort]
        solution['spectra'] = (solution['radius']/r_star)**2
    
    except (KeyError, ValueError) as e:
        error_message = 'One of the parameters to make up the model was missing or out of range.'
        model_key = 'rainout_0400_50_+0.0_0.70_0010_1.00'
        solution = {}
        with h5py.File(database_path) as f:
            solution['wv'] = f['/wavelength'][...][:-1]
            solution['spectra'] = f['/spectra/{}'.format(model_key)][...][:-1]
        closest_match = {'model_key': model_key, 'model_temperature': 400,
                'model_gravity': 50}
        inputs = input_args
    
    return solution, inputs, closest_match, error_message
