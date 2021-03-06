"""
Created on Jan 22, 2014

@author: Jens Luebben

Class implementing the plugin manager.
"""
import imp
from sys import argv
from os import listdir
try:
    from ConfigParser import ConfigParser
except ImportError:
    from configparser import ConfigParser
from lauescript.core.apd_printer import apd_printer
from sys import exit

all_managers = []


def get_plugin_manager(i=0):
    """
    Returns a reference to a plugin manager instance.
    :param i: Returns the ith manager.
    :return: Reference to a plugin manager instance.
    """
    return all_managers[i]


class PluginManager(object):
    """
    A class for managing plugins, cmd line options,
    output formatting, data logging and data exchange.
    """


    def __init__(self,
                 headline=None,
                 bottomline=None,
                 data=None,
                 argvs=None,
                 verbose=False,
                 headlines=True,
                 alpha=None,
                 delta=None,
                 omega=None,
                 config=None,
                 macro_file=None):
        """
        Initializes the Configuration instance. All arguments are
        optional and are used to control the behavior of the instance.

        headline: A string. The string is used as the argument when
                calling the printer.headline() method for the first
                time.
        bottomline: A string. The string is used as the argument when
                calling the printer.bottomline() method for the last
                time.
        data:    Any type of variable is accepted. The data can be
                accessed by the get_data() and set_data() methods.
        argvs:   A list of strings. If the cmdline arguments should
                  be controlled by the calling programm instead of
                  the user, this option can be used to overwrite
                  sys.argv.
        verbose: A boolean. Defines the initial state of the printer
                  instance used by the Configuration instance. The
                  state can be controlled after initialization by
                  calling the mute()/unmute() methods.
        headlines: A boolean. If False, called plugins do not print
                  an extra headline.
        alpha:   A function. The function must accept at least one
                  argument. The function will be called at the end
                  of the initialization and can be used to do any
                  preprocessing that is required before any plugins
                  are called. The function will get the instance
                  of the Configuration class as an argument.
        delta:   A function. The function must accept at least one
                  argument. The function will be called after every
                  call of a plugin and can be used to do any kind
                  of intermediate processing. The function will get
                  the instance of the Configuration class as an
                  argument.
        omega:   A function. The function must accept at least one
                  argument. The function will be called at the end
                  of the execute() method. The function will get
                  the instance of the Configuration class as an
                  argument.
        config:  Path to an INI file compatible with the ConfigParser
                  Module.
        macro_file: A String. Created macros will be stored in the
                    file with the path 'macro_file'.
        """
        all_managers.append(self)
        self.actions = []
        self.options = {}
        self.print_headlines = headlines
        if alpha:
            self.alpha = alpha
        if delta:
            self.delta = delta
        if omega:
            self.omega = omega

        self.printer_list = []
        self.reserved_keys = ['v', 'info', 'macro']

        self.config = ConfigParser()
        self.config.read(config)

        self.current_option = None

        self.variables = {}
        self.current_action = None
        self.bottomline = bottomline
        self.printer = apd_printer()
        self.set_variable(data)

        self.printer.first()
        self.printer.headline(headline)

        if not argvs:
            self.argv = argv
        else:
            self.argv = argvs
        if '-v' in self.argv:
            verbose = True
        if not verbose:
            self.printer.mute()

        self.macro_file = macro_file
        self.macros = {}
        if macro_file:
            self.process_macros()

        self.moduledepth = 0
        self.path = self.config.get('APD', 'PluginPath')
        self.scan_for_plugins()

        self.report(False)

        self.parse_argv(self.argv)

        self.printer('\nConfiguration complete.')
        self.start()
        #=======================================================================
        # self.preprocess()
        #=======================================================================

    def start(self):
        self.alpha(self)

    def get_raw_args(self):
        """
        Returns the list representing the cmd line arguments
        before they were parsed.
        """
        return self.argv

    def alpha(self, _):
        """
        Dummy alpha function.
        """
        pass

    def delta(self, _):
        """
        Dummy delta function.
        """
        pass

    def omega(self, _):
        """
        Dummy omega function.
        """
        pass

    def get_frequency_cutoff(self):
        """
        Deprecated method returning the frequency cutoff as defined
        in the config.py file.
        """
        return self.config.getint('Database', 'Frequency_cutoff')

    def register_variable(self, instance, name):
        """
        Registeres a new variable that will be accessible via the
        data exchange interface.

        'instance' is the reference to a variable.

        'name' is the name the variable should be accessed by via
        the 'get_variable' method.
        """
        self.variables[name] = instance

    def get_variable(self, name='data'):
        """
        Returns a reference to a previously registerd variable.

        'name' is the same name that was used to register the
        variable.
        """
        return self.variables[name]

    def set_variable(self, instance, name='data'):
        """
        Resets the value of the registered variable accessible by 'name'.
        """
        self.register_variable(instance, name)

    def exit(self, value=0):
        """
        Executes all print commands left in the plugin stack, prints a
        final bottomline and exits the program.
        """
        self.printer.unmute()
        for printer in self.printer_list:
            printer.exit()
        self.printer.bottomline(self.bottomline)
        self.printer.last()
        exit(value)

    def get_active_printer(self):
        """
        :return: Returns the reference to the APD_Printer instance on top
        of the printer stack. If the stack is empty, a reference to self.printer is returned.
        """
        try:
            return self.printer_list[-1]
        except IndexError:
            return self.printer

    def get_databasepath(self):
        """
        Deprecated method returning the databasepath specified in the config.py
        file.
        """
        return self.config.get('APD', 'DatabasePath')

    def get_config_value(self, section, entry):
        return self.config.get(section, entry)

    def get_config_valueInt(self, section, entry):
        return self.config.getint(section, entry)

    def get_config_valueFloat(self, section, entry):
        return self.config.getfloat(section, entry)

    def get_config_valueBool(self, section, entry):
        return self.config.getboolean(section, entry)

    def process_macros(self):
        """
        Method for storing and accessing macros.
        """
        if 'macro' in self.argv:
            i = self.argv.index('macro')
            use_macro = ARG(self.argv[i + 1])
            del self.argv[i + 1]
            del self.argv[i]
            if use_macro:
                state = use_macro[0]
                name = use_macro[1]
                if state == 'save':
                    self.add_macro(name)
                elif state == 'load':
                    self.read_macros()
                    if name in self.macros.keys():
                        self.activate_macro(name)

    def activate_macro(self, name):
        """
        Includes the macro defined by 'name' into the
        self.argv attributes.
        """
        new_argv = [self.argv[0]] + self.macros[name]
        try:
            new_argv += self.argv[2:]
        except:
            pass
        self.argv = new_argv

    def add_macro(self, name):
        """
        Uses 'name' as a reference to store the current
        cmd line options in a file.
        """
        try:
            self.read_macros()
            filepointer = open(self.macro_file, 'w')
        except:
            filepointer = open(self.macro_file, 'w')
        self.macros[name] = self.argv[1:]
        for name, args in self.macros.items():
            filepointer.write(name)
            for arg in args:
                filepointer.write(' ' + arg)
            filepointer.write('\n')
        self.unmute()
        self.printer('Adding new macro: {}.'.format(name))
        self.mute()
        filepointer.close()

    def read_macros(self):
        """
        Generates a macro dictionary from the file located
        at 'self.macrofile'.
        """
        filepointer = open(self.macro_file, 'r')
        for line in filepointer.readlines():
            if not line.lstrip().startswith('#'):
                line = [i.rstrip('\n') for i in line.split(' ') if i]
                self.macros[line[0]] = line[1:]
        filepointer.close()

    def mute(self):
        """
        Mutes the plugin manager instance.
        """
        self.printer.mute()

    def unmute(self):
        """
        Unmutes the plugin manager instance.
        """
        self.printer.unmute()

    def report(self, unmute=True):
        """
        Prints a table containing all plugin names and
        their corresponding cmdline keys.
        The optional argument 'unmute' can be set True
        to temporarely unmute the classe's printer.
        """
        if unmute:
            self.unmute()
        self.printer('Detected Plugins:\n')
        self.printer.table(['Key', 'Module'], head=True)
        for key, plugin in self.plugins.items():
            self.printer.table(['-' + key, str(plugin).split(' ')[1][1:-1]])
        self.printer.table(done=True)

        self.printer('\n')
        self.printer.table(['', 'reserved keywords'], head=True)
        for word in self.reserved_keys:
            self.printer.table(['', word])
        self.printer.table(done=True)
        if unmute:
            self.mute()

    def parse_argv(self, argv):
        """
        Parses the commandline string and assigns the specified
        parameters to the specified plugin. The order of the
        commands is used to determine the order of execution.
        The attribute .action is created containing a sorted
        list of commands to carry out.
        The attribute .options is created containing a dictionary
        that links a dictionary of options keyed to the corresponding
        action. The options dictionary contains at least the the
        key 'options' that holds a list of all options that have
        no additional arguments. Arguments with additional arguments
        , as specified in the plugins global 'OPTIONS_ARGUMENTS'
        variable, are stored in a list keyed to the option name.
        Currently, only one argument can be assigned to an option.
        Therefore the list holding the argument is always of length
        one.
        It is also possible to execute a module more than one
        time with different options. To manage the options in
        these cases action and option key get trailing underscores
        that are removed prior to execution.
        Actions and commands that can not be assigned to any
        module are ignored.
        Arguments that stand before any other Action are considered
        global and are stored in the .options dictionary under
        the key 'global'.

        """
        global_arg_opts = ['load', 'temp']
        self.printer('\nParsing commandline arguments.')
        self.actions = []
        self.options = {}
        key = 'global'
        arg_opt_key = 'options'
        self.options[key] = {'options': []}
        for arg in argv[1:]:
            #===================================================================
            # if arg.lstrip('-') in self.reserved_keys:
            #     key='global'
            #===================================================================
            if not arg.startswith('-'):
                try:
                    if arg in self.plugins[key.rstrip('_')].OPTION_ARGUMENTS:
                        arg_opt_key = arg
                        self.options[key][arg_opt_key] = []
                        continue
                except AttributeError:
                    pass
                except KeyError:
                    pass
                if key == 'global' and arg in global_arg_opts:
                    arg_opt_key = arg
                    self.options[key][arg_opt_key] = []
                    continue
                self.options[key][arg_opt_key].append(ARG(arg))
                arg_opt_key = 'options'
                if key == '_':
                    self.printer('   Ignoring argument: {}'.format(arg))
            else:
                key = self.check_key(arg.lstrip('-'))
                if not key.rstrip('_') in self.plugins.keys() and not key.rstrip('_') in self.reserved_keys:
                    self.printer('Unrecognized command: -{}'.format(key))
                    key = '_'
                self.actions.append(key)
                arg_opt_key = 'options'
                self.options[key] = {'options': []}
        try:
            del self.options['_']
            self.actions.remove('_')
        except:
            pass
        for arg in self.reserved_keys:
            try:
                self.actions.remove(arg)
            except:
                pass


    def check_key(self, key):
        """
        Prevents deleting the only reference to a plugin
        if the 'KEY' variable is equal to the filename.
        """
        if key in self.options.keys():
            key += '_'
            key = self.check_key(key)
        return key


    def scan_for_plugins(self):
        """
        Scans the programs plugin directory for plugins.
        To make a module visible as plugin the module
        must implement the global string variable 'KEY'.
        the value of 'KEY' is used to access the module
        in the .plugins attribute.
        """
        self.printer('Scanning for plugins in {}.'.format(self.path))
        files = listdir(self.path.replace('\\', '/'))
        files = [i[:-3] for i in files if i.endswith('.py') and not i == '__init__.py']
        self.plugins = {}
        renamelist = []
        for plugin in files:
            self.plugins[plugin] = imp.load_source(plugin, self.path + '/' + plugin + '.py')
            try:
                self.plugins[self.plugins[plugin].KEY] = self.plugins[plugin]
                if not self.plugins[plugin].KEY == plugin:
                    renamelist.append(plugin)
            except:
                self.printer('No KEY found in module {}. Ignoring module.'.format(plugin))
        for plugin in renamelist:
            del self.plugins[plugin]

    def get_plugin_path(self):
        """
        Returns a reference to the path searched for plugins.
        :return: String representing the plugin directory path.
        """
        return self.path


    def execute(self):
        """
        Subsequently calls all modules as specified by
        the cmdline arguments.
        """
        for action in self.actions:
            self.call(action)
        self.omega(self)
        self.printer.unmute()
        self.printer.bottomline(self.bottomline)
        self.printer.last()


    def call(self, action, options=None, headline=True):
        """
        Calls the 'run()' method of the plugin module
        referenced by 'action'. The optional argument
        'options' is a dictionary of the type defined
        by 'parse_argv()'. If not provided the
        corresponding values from self.options are
        taken.
        """
        self.current_headline_state = headline
        self.current_option = None
        self.current_action = action
        if options:
            self.current_option = options
        action = action.rstrip('_')
        self.moduledepth += 5
        self.printer_list.append(apd_printer(self.moduledepth, self.plugins[action].__name__))
        self.printer_list[-1].enter()
        self.plugins[action].run(self)
        if self.current_headline_state and self.print_headlines:
            self.printer_list[-1].bottomline()
        self.current_bottomline = None
        self.printer_list[-1].exit()
        self.printer_list = self.printer_list[:-1]
        self.moduledepth -= 5
        self.delta(self)


    def arg(self, key, global_arg=False):
        """
        Returns the value of the argument option linked to
        'key' or True/False if the option has no argument.
        If 'global_arg' is True, the global arguments are
        searched for the given key.
        If 'global_arg' is False, both, the module specific
        and the global arguments are searched. If the key
        is found in both, the module specific one is returned.
        """
        if self.current_option:
            return self.current_arg(key)
        value = False
        use = self.current_action

        if global_arg:
            use = 'global'
        if use in self.options.keys():
            try:
                value = self.options[use][key][0]
            except:
                if key in self.options[use]['options']:
                    value = True
        if not value and not global_arg:
            value = self.arg(key, True)
        if not value and hasattr(self.plugins[self.current_action],'OPTION_ARGUMENTS'):
            if key in self.plugins[self.current_action].OPTION_ARGUMENTS:
                try:
                    value = self.plugins[self.current_action].OPTION_ARGUMENTS[key]
                except TypeError:
                    value = None
                    print('Warning: OPTION_ARGUMENTS in module {} should be a dictionary type.'\
                        .format(self.plugins[self.current_action].__file__))

        return value

    def current_arg(self, key):
        """
        Is called when the current_option attribute is
        not 'None'.
        """
        value = False
        try:
            value = self.current_option[key][0]
        except:
            if key in self.current_option['options']:
                value = True
        return value


    def setup(self):
        """
        This method should be called by a plugin's 'run()'
        method before anything else to setup all module
        specific class attributes.
        """
        try:
            self.current_bottomline = self.plugins[self.current_action].BOTTOMLINE
        except:
            self.current_bottomline = None
        if self.current_headline_state and self.print_headlines:
            if not self.current_bottomline:
                self.printer_list[-1].headline()
            else:
                self.printer_list[-1].headline(self.plugins[self.current_action].HEADLINE)
        #=======================================================================
        # if not self.current_option:
        #     mo=self.options[self.current_action]
        # else:
        #     mo=self.current_option
        #=======================================================================

        return self.printer_list[-1]

    def clearSystemArgs(self):
        """
        Clears the sys.argv list. Use this method if a plugin calls into a library that makes use of sys.argv.
        Call restoreSystemArgs to restore the list.
        """
        import sys
        sys.argv = [self.argv[0]]

    def restoreSystemArgs(self):
        """
        Restores the sys.argv list.
        """
        import sys
        sys.argv = self.argv


class ARG(str):
    """
    Class representing a command line argument
    """

    def __init__(self, value):
        super(ARG, self).__init__(value)
        self.list = self.split(':')

    def __getitem__(self, i):
        try:
            return self.list[i]
        except:
            raise IndexError


