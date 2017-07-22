# -*- coding: utf-8 -*-

# Copyright 2017 IBM RESEARCH. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# =============================================================================

"""
Qasm Program Class

Authors: Andrew Cross
         Jay M. Gambetta <jay.gambetta@us.ibm.com>
         Ismael Faro <Ismael.Faro1@ibm.com>
         Jesus Perez <jesusper@us.ibm.com>
         Erick Winston <ewinston@us.ibm.com>
"""
# pylint: disable=line-too-long

import time
import random
from collections import Counter
import json
# use the external IBMQuantumExperience Library
from IBMQuantumExperience.IBMQuantumExperience import IBMQuantumExperience

# Stable Modules
from . import QuantumRegister
from . import ClassicalRegister
from . import QuantumCircuit
from . import QISKitException

# Beta Modules
from . import unroll
from . import qasm
from . import mapper

# Local Simulator Modules
from . import simulators

import sys
sys.path.append("..")
import qiskit.extensions.standard


class QuantumProgram(object):
    """ Quantum Program Class

     Class internal properties """

    # populate these in __init__()
    __ONLINE_BACKENDS = []
    __LOCAL_BACKENDS = []

    __quantum_program = {}
    __to_execute ={}
    __api = {}
    __api_config = {}

    """
    Elements that are not python identifiers or string constants are denoted
    by "--description (type)--". For example, a circuit's name is denoted by
    "--circuit name (string)--" and might have the value "teleport".

    __quantum_program =
        {
        --circuit name (string)--:
            {
            "circuit": --circuit object --,
            "execution":
                {  #### FILLED IN AFTER RUN -- JAY WANTS THIS MOVED DOWN ONE LAYER ####
                --backend name (string)--:
                    {
                    "compiled_circuit": --compiled quantum circuit object (DAG format) --,
                    "config":
                        {
                        "basis_gates": --comma separated gate names (string)--,
                        "coupling_map": --adjacency list (dict)--,
                        "layout": --layout computed by mapper (dict)--,
                        "shots": --shots (int)--,
                        "max_credits": --credits (int)--,
                        },
                    "data":
                        {  #### DATA CAN BE A DIFFERENT DICTIONARY FOR EACH BACKEND ####
                        "counts": {’00000’: XXXX, ’00001’: XXXXX},
                        "time"  : xx.xxxxxxxx
                        },
                    "status": --status (string)--
                    },
                },
            }
        }


    __to_execute =
        {
        --backend name (string)--:
            [
                {
                "name": --circuit name (string)--,
                "compiled_circuit": --compiled quantum circuit (DAG format)--,
                "config": --dictionary of additional config settings (dict)--
                    "coupling_map": --adjacency list (dict)--,
                    "basis_gates": --comma separated gate names (string)--,
                    "layout": --layout computed by mapper (dict)--,
                    "shots": (qasm only) --shots (int)--,
                    "max_credits" (online only): --credits (int)--,
                    "seed": (simulator only)--initial seed for the simulator (int)--,

                },
            ...
            ]
        }
    """
    # -- FUTURE IMPROVEMENTS --
    # TODO: for status results choose ALL_CAPS
    # TODO: coupling_map, basis_gates will move to config object

    def __init__(self, specs=None, name=""):
        self.__quantum_program = {}
        self.__quantum_registers = {}
        self.__classical_registers = {}
        self.__init_circuit = None
        self.__last_backend = ""
        self.__to_execute = {}
        self.__ONLINE_BACKENDS = []
        self.__LOCAL_BACKENDS = self.local_backends()
        self.mapper = mapper
        if specs:
            self.__init_specs(specs)

    # API functions
    def get_api_config(self):
        """Return the program specs"""
        return self.__api.req.credential.config

    def _setup_api(self, token, url, verify=True):
        try:
            self.__api = IBMQuantumExperience(token, {"url": url}, verify)
            self.__ONLINE_BACKENDS = self.online_backends()
            return True
        except Exception as err:
            print('ERROR in _quantumprogram._setup_api:', err)
            return False

    def set_api(self, token=None, url=None, verify=True):
        """Set the API conf"""
        if not token:
            token = self.__api_config["token"]
        else:
            self.__api_config["token"] = token
        if not url:
            url = self.__api_config["url"]
        else:
            self.__api_config["url"] = {"url": url}
        api = self._setup_api(token, url, verify)
        return api

    def set_api_token(self, token):
        """ Set the API Token """
        self.set_api(token=token)

    def set_api_url(self, url):
        """ Set the API url """
        self.set_api(url=url)

    def get_api(self):
        return self.__api

    def online_backends(self):

        """
        Queries network API if it exists.

        Returns
        -------
        List of online backends if the online api has been set or an empty
        list of it has not been set.
        """
        if self.get_api():
            return [backend['name'] for backend in self.__api.available_backends() ]
        else:
            return []

    def online_simulators(self):
        """
        Gets online simulators via QX API calls.

        Returns
        -------
        List of online simulator names.
        """
        simulators = []
        if self.get_api():
            for backend in self.__api.available_backends():
                if backend['simulator']:
                    simulators.append(backend['name'])
        return simulators

    def online_devices(self):
        """
        Gets online devices via QX API calls
        """
        devices = []
        if self.get_api():
            for backend in self.__api.available_backends():
                if not backend['simulator']:
                    devices.append(backend['name'])
        return devices

    def local_backends(self):
        """
        Get the local backends.
        """
        return simulators._localsimulator.local_backends()

    def available_backends(self):
        return self.__ONLINE_BACKENDS + self.__LOCAL_BACKENDS

    def get_backend_status(self, backend):
        """Return the online backend status via QX API call or by local
        backend is the name of the local or online simulator or experiment
        """

        if backend in self.__ONLINE_BACKENDS:
            return self.__api.backend_status(backend)
        elif  backend in self.__LOCAL_BACKENDS:
            return {'available': True}
        else:
            return {"status": "Error", "result": "This backend doesn't exist"}

    def get_backend_configuration(self, backend):
        """Return the configuration of the backend.

        Parameters
        ----------
        backend : str
           Name of the backend.

        Returns
        -------
        The configuration of the named backend.

        Raises
        ------
        If a configuration for the named backend can't be found
        raise a LookupError.
        """
        if self.get_api():
            for configuration in self.__api.available_backends():
                if configuration['name'] == backend:
                    return configuration
        for configuration in simulators.local_configuration:
            if configuration['name'] == backend:
                return configuration
        raise LookupError(
            'backend configuration for "{0}" not found'.format(backend))

    def get_backend_calibration(self, backend):
        """Return the online backend calibrations via QX API call
        backend is the name of the experiment
        """

        if backend in self.__ONLINE_BACKENDS:
            return self.__api.backend_calibration(backend)
        elif  backend in self.__LOCAL_BACKENDS:
            return {'calibrations': None}
        else:
            raise LookupError(
                'backend calibration for "{0}" not found'.format(backend))

    def get_backend_parameters(self, backend):
        """Return the online backend parameters via QX API call
        backend is the name of the experiment
        """

        if backend in self.__ONLINE_BACKENDS:
            return self.__api.backend_parameters(backend)
        elif  backend in self.__LOCAL_BACKENDS:
            return {'parameters': None}
        else:
            return {"status": "Error", "result": "This backend doesn't exist"}

    # Building parts of the program
    def create_quantum_registers(self, name, size):
        """Create a new set of Quantum Registers"""
        self.__quantum_registers[name] = QuantumRegister(name, size)
        print(">> quantum_registers created:", name, size)
        return self.__quantum_registers[name]

    def create_quantum_registers_group(self, registers_array):
        """Create a new set of Quantum Registers based on a array of that"""
        new_registers = []
        for register in registers_array:
            register = self.create_quantum_registers(
                register["name"], register["size"])
            new_registers.append(register)
        return new_registers

    def create_classical_registers(self, name, size):
        """Create a new set of Classical Registers"""
        self.__classical_registers[name] = ClassicalRegister(name, size)
        print(">> classical_registers created:", name, size)
        return self.__classical_registers[name]

    def create_classical_registers_group(self, registers_array):
        """Create a new set of Classical Registers based on a array of that"""
        new_registers = []
        for register in registers_array:
            new_registers.append(self.create_classical_registers(
                register["name"], register["size"]))
        return new_registers

    def create_circuit(self, name, qregisters=None, cregisters=None, circuit_object=None):
        """Create a new Quantum Circuit into the Quantum Program
        name is a string, the name of the circuit
        qregisters is an Array of Quantum Registers, can be String, by name or the object reference
        cregisters is an Array of Classical Registers, can be String, by name or the object reference
        """
        if not qregisters:
            qregisters = []
        if not cregisters:
            cregisters = []

        if not circuit_object:
            circuit_object = QuantumCircuit()
        self.__quantum_program[name] = {"name":name, "circuit": circuit_object}

        for register in qregisters:
            if isinstance(register, str):
                self.__quantum_program[name]['circuit'].add(self.__quantum_registers[register])
            else:
                self.__quantum_program[name]['circuit'].add(register)
        for register in cregisters:
            if isinstance(register, str):
                self.__quantum_program[name]['circuit'].add(self.__classical_registers[register])
            else:
                self.__quantum_program[name]['circuit'].add(register)

        return self.__quantum_program[name]['circuit']

    def get_quantum_registers(self, name):
        """Return a Quantum Register by name"""
        return self.__quantum_registers[name]

    def get_classical_registers(self, name):
        """Return a Classical Register by name"""
        return self.__classical_registers[name]

    def get_circuit(self, name):
        """Return a Circuit Object by name"""
        return self.__quantum_program[name]['circuit']

    def get_circuit_names(self):
        """Return all circuit names"""
        return list(self.__quantum_program.keys())

    def get_quantum_elements(self, specs=None):
        """Return the basic elements, Circuit, Quantum Registers, Classical Registers"""
        return self.__init_circuit, \
            self.__quantum_registers[list(self.__quantum_registers)[0]], \
            self.__classical_registers[list(self.__classical_registers)[0]]

    def load_qasm(self, name="", qasm_file=None, qasm_string=None,
                  basis_gates=None):
        """ Load qasm file
        qasm_file qasm file name
        """
        if not qasm_file and not qasm_string:
            print('"No filename provided')
            return {"status": "Error", "result": "No filename provided"}
        if not basis_gates:
            basis_gates = "u1,u2,u3,cx,id"  # QE target basis

        if name == "" and qasm_file:
            name = qasm_file

        circuit_object = qasm.Qasm(filename=qasm_file,
                                   data=qasm_string).parse()  # Node (AST)

        # TODO: add method to convert to QuantumCircuit object from Node
        self.__quantum_program[name] = {"circuit": circuit_object}

        return {"status": "COMPLETED", "result": 'all done'}

    def __init_specs(self, specs):
        """Populate the Quantum Program Object with initial Specs"""
        quantumr = []
        classicalr = []
        if "api" in specs:
            if specs["api"]["token"]:
                self.__api_config["token"] = specs["api"]["token"]
            if specs["api"]["url"]:
                self.__api_config["url"] = specs["api"]["url"]

        if "circuits" in specs:
            for circuit in specs["circuits"]:
                quantumr = self.create_quantum_registers_group(
                    circuit["quantum_registers"])
                classicalr = self.create_classical_registers_group(
                    circuit["classical_registers"])
                self.__init_circuit = self.create_circuit(name=circuit["name"],
                                                          qregisters=quantumr,
                                                          cregisters=classicalr)
        else:
            if "quantum_registers" in specs:
                print(">> quantum_registers created")
                quantumr = specs["quantum_registers"]
                self.create_quantum_registers(
                    quantumr["name"], quantumr["size"])
            if "classical_registers" in specs:
                print(">> quantum_registers created")
                classicalr = specs["classical_registers"]
                self.create_classical_registers(
                    classicalr["name"], classicalr["size"])
            if quantumr and classicalr:
                self.create_circuit(name=specs["name"],
                                    qregisters=quantumr["name"],
                                    cregisters=classicalr["name"])

    def add_circuit(self, name, circuit_object):
        """Add a new circuit based on an Object representation.
        name is the name or index of one circuit."""
        self.__quantum_program[name] = {"name":name, "circuit": circuit_object}
        return circuit_object

    def get_qasm_image(self, circuit):
        """Get image circuit representation from API."""
        pass

    def get_qasm(self, name):
        """get the circut by name.
        name of the circuit"""
        if name in self.__quantum_program:
            return self.__quantum_program[name]['circuit'].qasm()
        else:
            return {"status": "Error", "result": 'Circuit not found'}

    def get_qasms(self, list_circuit_name):
        """get the circut by name.
        name of the circuit"""
        qasm_source = []
        for name in list_circuit_name:
            qasm_source.append(self.get_qasm(name))
        return qasm_source


    ###############################################################
    # methods to compile quantum programs into __to_execute
    ###############################################################

    def compile(self, name_of_circuits, backend="local_qasm_simulator",
                config=None, silent=True, basis_gates=None, coupling_map=None,
                initial_layout=None, shots=1024, max_credits=3, seed=None):
        """Compile the circuits into the exectution list.

        This builds the internal "to execute" list which is list of quantum
        circuits to run on different backends.

        Args:
            name_of_circuits (list[str]): circuit names to be compiled.
            backend (str): a string representing the backend to compile to
            config (dict): a dictionary of configurations parameters for the
                compiler
            silent (bool): is an option to print out the compiling information
            or not
            basis_gates (str): a comma seperated string and are the base gates,
                               which by default are: u1,u2,u3,cx,id
            coupling_map (dict): A directed graph of coupling
                                {
                                control(int):
                                    [
                                    target1(int),
                                    target2(int),
                                    , ...
                                    ],
                                    ...
                                }
                                eg. {0: [2], 1: [2], 3: [2]}
            intial_layout (dict): A mapping of qubit to qubit
                                  {
                                    ("q", strart(int)): ("q", final(int)),
                                    ...
                                  }
                                  eg.
                                  {
                                    ("q", 0): ("q", 0),
                                    ("q", 1): ("q", 1),
                                    ("q", 2): ("q", 2),
                                    ("q", 3): ("q", 3)
                                  }
            shots (int): the number of shots
            max_credits (int): the max credits to use 3, or 5
            seed (int): the intial seed the simulatros use

        Returns:
            status done and populates the internal __to_exectute object

        Jay: currently basis_gates, coupling_map, intial_layout, shots,
             max_credits and seed are extra inputs but I would like them to go
             into the confg.
        """
        if name_of_circuits == []:
            return {"status": "Error", "result": 'No circuits'}
        for name in name_of_circuits:
            if name not in self.__quantum_program:
                return {"status": "Error", "result": "%s not in QuantumProgram" % name}
            if not basis_gates:
                basis_gates = "u1,u2,u3,cx,id"  # QE target basis
            # TODO: The circuit object has to have .qasm() method (be careful)
            dag_circuit = self._unroller_code(self.__quantum_program[name]['circuit'],
                                             basis_gates=basis_gates)
            final_layout = None
            # if a coupling map is given compile to the map
            if coupling_map:
                if not silent:
                    print("pre-mapping properties: %s"
                          % dag_circuit.property_summary())
                # Insert swap gates
                coupling = self.mapper.Coupling(coupling_map)
                if not silent:
                    print("initial layout: %s" % initial_layout)
                dag_circuit, final_layout = self.mapper.swap_mapper(
                    dag_circuit, coupling, initial_layout, trials=20, verbose=False)
                if not silent:
                    print("final layout: %s" % final_layout)
                # Expand swaps
                dag_circuit = self._unroller_code(dag_circuit)
                # Change cx directions
                dag_circuit = mapper.direction_mapper(dag_circuit, coupling)
                # Simplify cx gates
                mapper.cx_cancellation(dag_circuit)
                # Simplify single qubit gates
                dag_circuit = mapper.optimize_1q_gates(dag_circuit)
                if not silent:
                    print("post-mapping properties: %s"
                          % dag_circuit.property_summary())

            if backend not in self.__to_execute:
                self.__to_execute[backend] = []

            # making the job to be added to __to_exectute
            job = {}
            job["name"] = name
            # config parameters used by the runner
            if config is None:
                config = {}  # default to empty config dict
            job["config"] = config
            job["config"]["coupling_map"] = coupling_map # TODO: why do we want this
            job["config"]["layout"] = final_layout # TODO: why do we want this
            job["config"]["basis_gates"] = basis_gates # TODO: why do we want this
            job["config"]["shots"] = shots
            job["config"]["max_credits"] = max_credits
            if seed is None:
                job["config"]["seed"] = random.random() # TODO: we should only add if simulator
            else:
                job["config"]["seed"] = seed
            # the compuled circuit to be run saved as a dag
            job["compiled_circuit"] = dag_circuit
            # add job to the __to_exectute
            self.__to_execute[backend].append(job)
        return {"status": "COMPLETED", "result": 'all done'}

    def get_compiled_configuration(self, name, backend=None):
        """Get the compiled layout for the named circuit and backend.

        If backend is None, it defaults to the last backend.

        Args:
            name (str):  the circuit name
            backend (str): the name of hte backend

        Returns:
            the config of the circuit.
        """
        if not backend:
            backend = self.__last_backend
        try:
            for configuration in self.__to_execute[backend]:
                if configuration['name'] == name:
                    return configuration["config"]
        except KeyError:
            return "No compiled configurations for this circuit"

    def delete_execution_list(self):
        """Clears the exectution list.

        Args:
            None
        Returns:
            Clears the internal self.__to_execute.
        """
        self.__to_execute = {}

    def get_execution_list(self, verbose=False):
        """Print the compiled circuits that are ready to run.

        Args:
            verbose (bool): controls how much is returned.
        """
        for backend, jobs in self.__to_execute.items():
            print("%s:" % backend)
            for job in jobs:
                if not verbose:
                    print("  %s" % job["name"])
                else:
                    print("  %s:" % job["name"])
                    print("    shots = %d" % job["config"]["shots"])
                    print("    max_credits = %d" % job["config"]["max_credits"])
                    print("    seed (simulator only) = %d" % job["config"]["seed"])
                    print("    compiled_circuit =")
                    print("// *******************************************")
                    parsed=json.loads(self._dag2json(job["compiled_circuit"]))
                    print(json.dumps(parsed, indent=4, sort_keys=True))
                    print("// *******************************************")

    def _dag2json(self, dag_circuit):
        """Make a Json representation of the circuit.

        Takes a circuit dag and returns json circuit obj. This is an internal
        function.

        Args:
            dag_ciruit (dag object): a dag representation of the circuit

        Returns:
            the json version of the dag

        JAY: I think this needs to become a method like .qasm() for the DAG.
        """
        qasm_circuit = dag_circuit.qasm(qeflag=True)
        basis_gates = "u1,u2,u3,cx,id"  # QE target basis
        unroller = unroll.Unroller(qasm.Qasm(data=qasm_circuit).parse(), unroll.JsonBackend(basis_gates.split(",")))
        json_circuit = unroller.execute()
        return json_circuit

    def _unroller_code(self, dag_ciruit, basis_gates=None):
        """ Unroll the code.

        Circuit is the circuit to unroll using the DAG representation.
        This is an internal function.

        Args:
            dag_ciruit (dag object): a dag representation of the circuit
            basis_gates (str): a comma seperated string and are the base gates,
                               which by default are: u1,u2,u3,cx,id
        Return:
            dag_ciruit (dag object): a dag representation of the circuit
                                     unrolled to basis gates

        JAY: Why do we need this it could just be two lines in compile.
        """
        if not basis_gates:
            basis_gates = "u1,u2,u3,cx,id"  # QE target basis
        unrolled_circuit = unroll.Unroller(qasm.Qasm(data=dag_ciruit.qasm()).parse(),
                                           unroll.CircuitBackend(basis_gates.split(",")))
        circuit_unrolled = unrolled_circuit.execute()
        return circuit_unrolled

    ###############################################################
    # methods to ran quantum programs (run __to_execute)
    ###############################################################

    def run(self, wait=5, timeout=60, silent=False):
        """Run a program (a pre-compiled quantum program).

        All input for run comes from self.__to_execute

        Args:
            wait (int): wait time is how long to check if the job is completed
            timeout (int): is time until the execution stops
            silent (bool): is an option to print out the running information or
            not

        Returns:
            status done and populates the internal __quantum_program with the
            data
        """
        for backend in self.__to_execute:
            self.__last_backend = backend
            if backend in self.__ONLINE_BACKENDS:
                last_shots = -1
                last_max_credits = -1
                jobs = []
                for job in self.__to_execute[backend]:
                    jobs.append({'qasm': job["compiled_circuit"].qasm(qeflag=True)})
                    shots = job["config"]["shots"]
                    max_credits = job["config"]["max_credits"]
                    if last_shots == -1:
                        last_shots = shots
                    else:
                        if last_shots != shots:
                            # Clear the list of compiled programs to execute
                            self.__to_execute = {}
                            return {"status": "Error", "result":'Online backends only support job batches with equal numbers of shots'}
                    if last_max_credits == -1:
                        last_max_credits = max_credits
                    else:
                        if last_max_credits != max_credits:
                            # Clear the list of compiled programs to execute
                            self.__to_execute = {}
                            return  {"status": "Error", "result":'Online backends only support job batches with equal max credits'}

                if not silent:
                    print("running on backend: %s" % (backend))
                output = self.__api.run_job(jobs, backend, last_shots, last_max_credits)
                if 'error' in output:
                    # Clear the list of compiled programs to execute
                    self.__to_execute = {}
                    return {"status": "Error", "result": output['error']}
                job_result = self._wait_for_job(output['id'], wait=wait, timeout=timeout, silent=silent)

                if job_result['status'] == 'Error':
                    # Clear the list of compiled programs to execute
                    self.__to_execute = {}
                    return job_result
            else:
                jobs = []
                for job in self.__to_execute[backend]:
                    jobs.append({"compiled_circuit": self._dag2json(job["compiled_circuit"]),
                                 "config": job["config"]})
                if not silent:
                    print("running on backend: %s" % (backend))
                if backend in self.__LOCAL_BACKENDS:
                    job_result = self.run_local_simulator(backend, jobs)
                else:
                    # Clear the list of compiled programs to execute
                    self.__to_execute = {}
                    return {"status": "Error", "result": 'Not a local simulator'}
            if backend in self.__ONLINE_BACKENDS:
                assert len(self.__to_execute[backend]) == len(job_result["qasms"]), "Internal error in QuantumProgram.run(), job_result"
            else:
                assert len(self.__to_execute[backend]) == len(job_result), "Internal error in QuantumProgram.run(), job_result"
            # Fill data into self.__quantum_program for this backend
            index = 0
            for job in self.__to_execute[backend]:
                name = job["name"]
                if name not in self.__quantum_program:
                    # Clear the list of compiled programs to execute
                    self.__to_execute = {}
                    return {"status": "Error", "result": "Internal error, circuit not found"}
                if not "execution" in self.__quantum_program[name]:
                    self.__quantum_program[name]["execution"]={}
                # We override the results
                if backend not in self.__quantum_program[name]["execution"]:
                    self.__quantum_program[name]["execution"][backend] = {}
                # TODO: return date, executionId, ...
                self.__quantum_program[name]["execution"][backend]["compiled_circuit"] = job["compiled_circuit"]
                self.__quantum_program[name]["execution"][backend]["config"]=job["config"]
                #for field in ["coupling_map", "basis_gates", "shots", "max_credits", "seed", "layout"]:
                #    self.__quantum_program[name]["execution"][backend]["config"][field] = job[field]
                # results filled in
                if backend in self.__ONLINE_BACKENDS:
                    self.__quantum_program[name]["execution"][backend]["data"] = job_result["qasms"][index]["result"]["data"]
                    self.__quantum_program[name]["execution"][backend]["status"] = job_result["qasms"][index]["status"]
                else:
                    self.__quantum_program[name]["execution"][backend]["data"] = job_result[index]["data"]
                    self.__quantum_program[name]["execution"][backend]["status"] = job_result[index]["status"]

                index += 1

        # Clear the list of compiled programs to execute
        self.delete_execution_list()

        return  {"status": "COMPLETED", "result": 'all done'}

    def _wait_for_job(self, jobid, wait=5, timeout=60, silent=False):
        """Wait until all online ran jobs are 'COMPLETED'.

        Args:
            jobids:  is a list of id strings.
            wait (int):  is the time to wait between requests, in seconds
            timeout (int):  is how long we wait before failing, in seconds
            silent (bool): is an option to print out the running information or
            not

        Returns:
            A list of results that correspond to the jobids.
        """
        timer = 0
        timeout_over = False
        job_result = self.__api.get_job(jobid)
        if 'status' not in job_result:
            from pprint import pformat
            raise Exception("get_job didn't return status: %s" % (pformat(job)))
        while job_result['status'] == 'RUNNING':
            if timer >= timeout:
                return {"status": "Error", "result": "Time Out"}
            time.sleep(wait)
            timer += wait
            if not silent:
                print("status = %s (%d seconds)" % (job_result['status'], timer))
            job_result = self.__api.get_job(jobid)

            if 'status' not in job_result:
                from pprint import pformat
                raise Exception("get_job didn't return status: %s" % (pformat(job_result)))
            if job_result['status'] == 'ERROR_CREATING_JOB' or job_result['status'] == 'ERROR_RUNNING_JOB':
                return {"status": "Error", "result": job_result['status']}

        # Get the results
        return job_result

    def run_local_simulator(self, backend, jobs):
        """Run a program of compiled quantum circuits on the local machine.

        Args:
          backend (str): the name of the local simulator to run
          jobs: list of dicts {"compiled_circuit": simulator input data,
                "config": integer num shots}

        Returns:
          Dictionary of form,
          job_results =
            [
                {
                "data": DATA,
                "status": DATA,
                },
                ...
            ]
        }
        """
        job_results = []
        for job in jobs:
            one_result = {'result': None, 'status': "Error"}
            local_simulator = simulators.LocalSimulator(backend, job)
            local_simulator.run()
            this_result = local_simulator.result()
            job_results.append(this_result)
        return job_results

    def execute(self, name_of_circuits, backend="local_qasm_simulator",
                config=None, wait=5, timeout=60, silent=False, basis_gates=None,
                coupling_map=None, initial_layout=None, shots=1024,
                max_credits=3, seed=None):

        """Execute, compile, and run an array of quantum circuits).

        This builds the internal "to execute" list which is list of quantum
        circuits to run on different backends.

        Args:
            name_of_circuits (list[str]): circuit names to be compiled.
            backend (str): a string representing the backend to compile to
            config (dict): a dictionary of configurations parameters for the
                compiler
            wait (int): wait time is how long to check if the job is completed
            timeout (int): is time until the execution stops
            silent (bool): is an option to print out the compiling information
            or not
            basis_gates (str): a comma seperated string and are the base gates,
                               which by default are: u1,u2,u3,cx,id
            coupling_map (dict): A directed graph of coupling
                                {
                                control(int):
                                    [
                                    target1(int),
                                    target2(int),
                                    , ...
                                    ],
                                    ...
                                }
                                eg. {0: [2], 1: [2], 3: [2]}
            intial_layout (dict): A mapping of qubit to qubit
                                  {
                                  ("q", strart(int)): ("q", final(int)),
                                  ...
                                  }
                                  eg.
                                  {
                                  ("q", 0): ("q", 0),
                                  ("q", 1): ("q", 1),
                                  ("q", 2): ("q", 2),
                                  ("q", 3): ("q", 3)
                                  }
            shots (int): the number of shots
            max_credits (int): the max credits to use 3, or 5
            seed (int): the intial seed the simulatros use

        Returns:
            status done and populates the internal __quantum_program with the
            data

        Jay: currently basis_gates, coupling_map, intial_layout, shots,
            max_credits, and seed are extra inputs but I would like them to go
            into the config
        """
        self.compile(name_of_circuits, backend=backend, config=config,
                     silent=silent, basis_gates=basis_gates,
                     coupling_map=coupling_map, initial_layout=initial_layout,
                     shots=shots, max_credits=max_credits, seed=seed)
        output = self.run(wait=wait, timeout=timeout, silent=silent)
        return output


    ###############################################################
    # methods to process the quantum program after it has been run
    ###############################################################

    def get_ran_qasm(self, name, backend=None):
        """Get the ran qasm for the named circuit and backend.

        If backend is None, it defaults to the last backend.
        Args:
            name (str): the name of the quantum circuit.
            backend (str): the name of the backend the data was run on.

        Returns:
            A text version of the qasm file that has been run.
        """
        if not backend:
            backend = self.__last_backend
        try:
            return self.__quantum_program[name]["execution"][backend]["compiled_circuit"].qasm()
        except KeyError:
            return "No qasm has been ran for this circuit"

    def get_data(self, name, backend=None):
        """Get the data of cicuit name.

        The data format will depend on the backend. For a real device it
        will be for the form
            "counts": {’00000’: XXXX, ’00001’: XXXX},
            "time"  : xx.xxxxxxxx
        for the qasm simulators of 1 shot
            'quantum_state': array([ XXX,  ..., XXX]),
            'classical_state': 0
        for the qasm simulators of n shots
            'counts': {'0000': XXXX, '1001': XXXX}
        for the unitary simulators
            'unitary': np.array([[ XX + XXj
                                   ...
                                   XX + XX]
                                 ...
                                 [ XX + XXj
                                   ...
                                   XX + XXj]]
        Args:
            name (str): the name of the quantum circuit.
            backend (str): the name of the backend the data was run on.

        Returns:
            A dictionary of data for the different backends.
        """
        if not backend:
            backend = self.__last_backend
        try:
            return self.__quantum_program[name]['execution'][backend]['data']
        except KeyError:
            return {"status": "Error", "result": 'Error in circuit name'}

    def get_counts(self, name, backend=None):
        """Get the histogram data of cicuit name.

        The data from the a qasm circuit is dictionary of the format
        {’00000’: XXXX, ’00001’: XXXXX}.

        Args:
            name (str): the name of the quantum circuit.
            backend (str): the name of the backend the data was run on.

        Returns:
            A dictionary of counts {’00000’: XXXX, ’00001’: XXXXX}.
        """
        if not backend:
            backend = self.__last_backend
        try:
            return self.__quantum_program[name]['execution'][backend]['data']['counts']
        except KeyError:
            return {"status": "Error", "result": 'Error in circuit name'}

    def average_data(self, name, observable):
        """Compute the mean value of an diagonal observable.

        Takes in an observable in dictionary format and then
        calculates the sum_i value(i) P(i) where value(i) is the value of
        the observable for state i.

        Args:
            name (str): the name of the quantum circuit
            obsevable (dict): The observable to be averaged over. As an example
            ZZ on qubits equals {"00": 1, "11": 1, "01": -1, "10": -1}

        Returns:
            a double for the average of the observable
        """
        counts = self.get_counts(name)
        temp = 0
        tot = sum(counts.values())
        for key in counts:
            if key in observable:
                temp += counts[key] * observable[key] / tot
        return temp
