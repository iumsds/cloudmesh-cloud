import os
import sys
import shutil
import oyaml as yaml
from base64 import b64encode, b64decode
from cloudmesh.common.FlatDict import flatten
from cloudmesh.common.Printer import Printer
from cloudmesh.common.Shell import Shell
from cloudmesh.common.console import Console
from cloudmesh.common.util import banner
from cloudmesh.common.util import path_expand, writefile
from cloudmesh.configuration.Config import Config
# from cloudmesh.security.encrypt import EncryptFile
from cloudmesh.shell.command import PluginCommand
from cloudmesh.shell.command import command, map_parameters
from cloudmesh.common.util import path_expand
from cloudmesh.security.encrypt import CmsEncryptor, KeyHandler, CmsHasher
from progress.bar import Bar

class ConfigCommand(PluginCommand):

    # see https://github.com/cloudmesh/client/blob/master/cloudmesh_client/shell/plugins/KeyCommand.py
    # see https://github.com/cloudmesh/client/blob/master/cloudmesh_client/shell/plugins/AkeyCommand.py

    # noinspection PyUnusedLocal
    @command
    def do_config(self, args, arguments):
        """
        ::

           Usage:
             config  -h | --help
             config cat [less]
             config check
             config secinit
             config encrypt [SOURCE] [--keep]
             config decrypt [SOURCE]
             config edit [ATTRIBUTE]
             config set ATTRIBUTE=VALUE
             config get ATTRIBUTE [--output=OUTPUT]
             config value ATTRIBUTE
             config ssh keygen
             config ssh verify
             config ssh check
             config ssh pem
             config cloud verify NAME [KIND]
             config cloud edit [NAME] [KIND]
             config cloud list NAME [KIND] [--secrets]


           Arguments:
             SOURCE           the file to encrypted or decrypted.
                              an .enc is added to the filename or removed form it
                              dependent of if you encrypt or decrypt
             ATTRIBUTE=VALUE  sets the attribute with . notation in the
                              configuration file.
             ATTRIBUTE        reads the attribute from the container and sets it
                              in the configuration file
                              If the attribute is a password, * is written instead
                              of the character included

           Options:
              --name=KEYNAME     The name of a key
              --output=OUTPUT    The output format [default: yaml]
              --secrets          Print the secrets. Use carefully.

           Description:

             config check
                checks if the ssh key ~/.ssh/id_rsa has a password. Verifies it
                through entering the passphrase

             Key generation

                Keys must be generated with

                    ssh-keygen -t rsa -m pem
                    openssl rsa -in ~/.ssh/id_rsa -out ~/.ssh/id_rsa.pem

                or
                    cms config ssh keygen

                Key validity can be checked with

                    cms config check

                The key password can be verified with

                    cms config verify


                ssh-add

                cms config encrypt ~/.cloudmesh/cloudmesh.yaml
                cms config decrypt ~/.cloudmesh/cloudmesh.yaml


                config set ATTRIBUTE=VALUE

                    config set profile.name=Gregor

                In case the ATTRIBUTE is the name of a cloud defined under
                cloudmesh.cloud, the value will be written into the credentials
                attributes for that cloud this way you can safe a lot of
                typing. An example is

                    cms config set aws.AWS_TEST=Gregor

                which would write the AWS_TEST attribute in the credentials
                of the cloud aws. This can naturally be used to set for
                example username and password.

        """
        # d = Config()                #~/.cloudmesh/cloudmesh.yaml
        # d = Config(encryted=True)   # ~/.cloudmesh/cloudmesh.yaml.enc

        map_parameters(arguments, "keep", "secrets", "output")

        source = arguments.SOURCE or path_expand("~/.cloudmesh/cloudmesh.yaml")
        destination = source + ".enc"

        if arguments.cloud and arguments.edit and arguments.NAME is None:
            path = path_expand("~/.cloudmesh/cloudmesh.yaml")
            print(path)
            Shell.edit(path)
            return ""

        cloud = arguments.NAME
        kind = arguments.KIND
        if kind is None:
            kind = "cloud"

        configuration = Config()



        if arguments.cloud and arguments.verify:
            service = configuration[f"cloudmesh.{kind}.{cloud}"]

            result = {"cloudmesh": {"cloud": {cloud: service}}}

            action = "verify"
            banner(
                f"{action} cloudmesh.{kind}.{cloud} in ~/.cloudmesh/cloudmesh.yaml")

            print(yaml.dump(result))

            flat = flatten(service, sep=".")

            for attribute in flat:
                if "TBD" in str(flat[attribute]):
                    Console.error(
                        f"~/.cloudmesh.yaml: Attribute cloudmesh.{cloud}.{attribute} contains TBD")

        elif arguments.cloud and arguments.list:
            service = configuration[f"cloudmesh.{kind}.{cloud}"]
            result = {"cloudmesh": {"cloud": {cloud: service}}}

            action = "list"
            banner(
                f"{action} cloudmesh.{kind}.{cloud} in ~/.cloudmesh/cloudmesh.yaml")

            lines = yaml.dump(result).split("\n")
            secrets = not arguments.secrets
            result = Config.cat_lines(lines, mask_secrets=secrets)
            print (result)

        elif arguments.cloud and arguments.edit:

            #
            # there is a duplicated code in config.py for this
            #
            action = "edit"
            banner(
                f"{action} cloudmesh.{kind}.{cloud}.credentials in ~/.cloudmesh/cloudmesh.yaml")

            credentials = configuration[f"cloudmesh.{kind}.{cloud}.credentials"]

            print(yaml.dump(credentials))

            for attribute in credentials:
                if "TBD" in credentials[str(attribute)]:
                    value = credentials[attribute]
                    result = input(f"Please enter {attribute}[{value}]: ")
                    credentials[attribute] = result

            # configuration[f"cloudmesh.{kind}.{cloud}.credentials"] = credentials

            print(yaml.dump(
                configuration[f"cloudmesh.{kind}.{cloud}.credentials"]))

        elif arguments["edit"] and arguments["ATTRIBUTE"]:

            attribute = arguments.ATTRIBUTE

            config = Config()

            config.edit(attribute)

            config.save()

            return ""


        elif arguments.cat:

            content = Config.cat()

            import shutil
            columns, rows = shutil.get_terminal_size(fallback=(80, 24))

            lines = content.split("\n")

            counter = 1
            for line in lines:
                if arguments.less:
                    if  counter % (rows-2) == 0:
                        x = input().split("\n")[0].strip()
                        if x !='' and x in 'qQxX' :
                            return ""
                print (line)
                counter += 1

            return ""

        elif arguments.check and not arguments.ssh:

            Config.check()

        elif arguments.encrypt:
            """ 
            Encrypts the keys listed within Config.secrets()

            Assumptions:
              1. ```cms init``` or ```cms config secinit``` has been executed
              2. that the secidr is ~/.cloudmesh/security and exists [secinit]
              3. Private key has same base name as public key
              4. Public key ends with .pub, .pem, or any .[3 char combo]
              5. Private key is in PEM format
              6. The cloudmesh config version has not changed since encrypt
                 This means data must re-encrypt upon every config upgrade

            Note: this could be migrated to Config() directly
            """
            # Secinit variables: location where keys are stored
            cmssec_path = path_expand("~/.cloudmesh/security")
            gcm_path = f"{cmssec_path}/gcm"
            
            # Helper variables
            config = Config()
            d = config.dict() # dictionary of config 
            secrets = config.secrets() #secret value key names
            ch = CmsHasher() # Will hash the paths to produce file name
            kh = KeyHandler() # Loads the public or private key bytes
            ce = CmsEncryptor() # Assymmetric and Symmetric encryptor

            # Get the public key
            kp = config.get_value('cloudmesh.profile.publickey')
            pub = kh.load_key(kp, "PUB", "SSH", False)

            #TODO: file reversion on failed encryption or decryption
            bar = Bar('Cloudmesh Config Encryption', max=len(secrets))
            for secret in secrets: # for each secret defined in Config.secrets()
                paths = config.get_path(secret, d) # get all paths to key
                for path in paths: # for each path that reaches the key
                    # Hash the path to create a base filename
                    # MD5 is acceptable since security does not rely on hiding the path
                    h = ch.hash_data(path, "MD5", "b64", True)
                    fp = f"{gcm_path}/{h}" #path to filename for key and nonce
                    if os.path.exists(f"{fp}.key"):
                        Console.error(f"already encrypted: {path}")
                    else:
                        ## Additional Authenticated Data: the cloudmesh version
                        # number is used to future-proof for version attacks 
                        aad = config.get_value('cloudmesh.version')

                        # Get plaintext data from config
                        pt = config.get_value(path)
                        b_pt = pt.encode()

                        # Encrypt the cloudmesh.yaml attribute value
                        k, n, ct = ce.encrypt_aesgcm(data = b_pt, aad = aad.encode())

                        ## Write ciphertext contents
                        #TODO: Ensure the value set is within ""
                        #TODO: Ensure decryption removes "" wrapping
                        ct = b64encode(ct).decode()
                        config.set(path, f"{ct}")

                        # Encrypt symmetric key with users public key
                        k_ct = ce.encrypt_rsa(pub = pub, pt = k)
                        ## Write key to file
                        k_ct = b64encode(k_ct).decode()
                        fk = f"{fp}.key" # use hashed filename with indicator
                        writefile(filename = fk , content = k_ct, permissions = 0o600)

                        # Encrypt nonce with users private key
                        n_ct = ce.encrypt_rsa(pub = pub, pt = n)
                        ## Write nonce to file
                        n_ct = b64encode(n_ct).decode()
                        fn = f"{fp}.nonce"
                        writefile(filename = fn, content = n_ct, permissions = 0o600)
                bar.next()
            bar.finish()
            Console.ok("Success")

        elif arguments.decrypt:

            if ".enc" not in source:
                source = source + ".enc"
            else:
                destination = source.replace(".enc", "")

            if not os.path.exists(source):
                Console.error(f"encrypted file {source} does not exist")
                sys.exit(1)

            if os.path.exists(destination):
                Console.error(
                    f"decrypted file {destination} does already exist")
                sys.exit(1)

            e = EncryptFile(source, destination)

            e.decrypt(source)
            Console.ok(f"{source} --> {source}")

            Console.ok("file decrypted")
            return ""

        elif arguments.ssh and arguments.verify:

            e = EncryptFile(source, destination)

            e.pem_verify()

        elif arguments.ssh and arguments.check:

            e = EncryptFile(source, destination)

            key = path_expand("~/.ssh/id_rsa")
            r = e.check_key(key)
            if r:
                Console.ok(f"Key {key} is valid")
            # does not work as it does not change it to pem format
            # e.check_passphrase()

        elif arguments.ssh and arguments.pem:

            e = EncryptFile(source, destination)

            r = e.pem_create()

        elif arguments.set:

            config = Config()
            clouds = config["cloudmesh.cloud"].keys()

            line = arguments["ATTRIBUTE=VALUE"]
            attribute, value = line.split("=", 1)

            cloud, field = attribute.split(".",1)

            if cloud in clouds:
                attribute = f"cloudmesh.cloud.{cloud}.credentials.{field}"

            elif not attribute.startswith("cloudmesh."):
                attribute = f"cloudmesh.{attribute}"

            config[attribute] = value
            config.save()

        elif arguments.value:

            config = Config()

            attribute = arguments.ATTRIBUTE
            if not attribute.startswith("cloudmesh."):
                attribute = f"cloudmesh.{attribute}"

            try:
                value = config[attribute]
                if type(value) == dict:
                    raise Console.error("the variable is a dict")
                else:
                    print(f"{value}")

            except Exception as e:
                print (e)
                return ""

        elif arguments.secinit:
            secpath = "~/.cloudmesh/security"
            gcm_path = f"{secpath}/gcm"
            
            if not os.path.isdir(gcm_path):
                Shell.mkdir(gcm_path)

        elif arguments.get:

            print ()

            config = Config()
            clouds = config["cloudmesh.cloud"].keys()

            attribute = arguments.ATTRIBUTE

            try:
                cloud, field = attribute.split(".",1)
                field = f".{field}"
            except:
                cloud = attribute
                field = ""

            if cloud in clouds:
                attribute = f"cloudmesh.cloud.{cloud}{field}"
            elif not attribute.startswith("cloudmesh."):
                attribute = f"cloudmesh.{attribute}"

            try:
                value = config[attribute]
                if type(value) == dict:
                    print(Printer.write(value, output=arguments.output))
                else:
                    print(f"{attribute}={value}")

            except Exception as e:
                print (e)
                return ""


        elif arguments.ssh and arguments.keygen:

            e = EncryptFile(source, destination)

            e.ssh_keygen()



        return ""
