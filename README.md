# victoria_email
Victoria plugin for managing the Glasswall Rebuild for Email platform.

## Features
- Load testing SMTP endpoints

## User guide

### Prerequisites
- Python 3.7+
- Pip

### Installation
```
$ pip install -U victoria_email
```

### Operation

#### Configuration
This plugin expects a section in your Victoria config file's `plugins_config` or
`plugins_config_location`. Its key is `email`. 

An easy way to edit your config file if you have VSCode installed is by running:
`code $(victoria config path)`.

A full config example is:
```yaml
email:
  load_test:
    mail_send_function_endpoint: https://sls-weur-dev-going-postal.azurewebsites.net/api/send
    mail_send_function_code: <the code to access the Azure Function>
    tenant_id: <the tenant ID to attach to the email>
    timeout: 10.0
  mail_toil:
    service_bus_connection_strings:
      <cluster-name>: <encrypted data>

    # these are the queues we want to check for dead letters
    queues:
      - "queues"
      - "you"
      - "want"
      - "to"
      - "check"

    storage_accounts:
      <cluster-name>: <encrypted data>

    # this is the directory to use when backing up replayed messages
    vault_dir: "vault"
```

The `load_test` and `mail_toil` sections are both optional. If you don't need
mail toil or load testing functionality you can leave it out. The plugin will
give you a warning if you're missing either and attempting to use the
functionality.

##### Encrypting data for config values
In the `mail_toil` section of the config, the `service_bus_connection_strings`
and `storage_accounts` fields expect data that is encrypted. This can be
achieved with the pre-build `victoria encrypt` command. Details on this
can be found in [the documentation](https://sre.glasswallsolutions.com/victoria/user-guide.html#cloud-encryption)
but for a whistlestop tour:

1. Make sure you've set up your [Victoria cloud encryption backend](https://sre.glasswallsolutions.com/victoria/user-guide.html#azure).
2. Find a service bus you want to use with MailToil in the Azure Portal, and
   click on 'shared access policies' on the sidebar. Click on the policy here.
   Copy the 'primary connection string' from here.
3. Paste it into the following Victoria command:
   ```
   $ victoria encrypt data <the connection string>
   ```
4. The command should output a YAML object containing fields `data`, `iv`, `key`, and `version`.
   This is the encrypted connection string and can be safely stored in config.
   Put this YAML object in a key in your `service_bus_connection_strings` config field.
   The key name should be the cluster name, i.e. for uksprod1:
   ```yaml
   mail_toil:
     service_bus_connection_strings:
       uksprod1:
         data: <snip>
         iv: <snip>
         key: <snip>
         version: <snip>
   ```
5. Continue to do this for all of the service buses.
6. For storage accounts, follow the same steps, except for step 2. Instead:
   Find a storage account you want to use with MailToil in Azure Portal, and
   click on 'Access keys' on the sidebar. Copy the `key1` connection string from
   here.

#### Load testing
The `loadtest` command can be used to load test an SMTP endpoint.

It accepts the following **required** arguments:
- `-e`, `--endpoint`: The SMTP endpoint to send to, with optional port i.e. 
  `smtp.example.com:465`. If the port is unspecified, i.e. `smtp.example.com`
  then port 25 is used.
- `-r`, `--recipient`: The email address to send mail to, i.e. `test@example.com`.
- `-s`, `--sender`: The email address to send mail from, i.e. `test@example.com`.

Running with just the required arguments will send a single test.

It also accepts the following **optional** arguments:
- `-n`, `--frequency`: The number of tests to send per second. Defaults to 1.
- `-t`, `--duration`: The number of seconds to run the test for. Defaults to 1.

All of this information can be found by running `victoria email loadtest -h`.

Example of sending a single email:
```
$ victoria email loadtest -e smtp.example.com -s test@example.com -r test@example.com
```

Example of sending 46 mails per second for 60 seconds:
```
$ victoria email loadtest -e smtp.example.com -n 46 -t 60 -s test@example.com -r test@example.com
```

Example of sending using a different port than port 25:
```
$ victoria email loadtest -e smtp.example.com:465 -s test@example.com -r test@example.com
```

#### Sending email
The `send` command can be used to send single emails (based on a YAML manifest
format) to an SMTP endpoint.

It accepts one argument, the path to the manifest file to send.

The format of the manifest file is as follows:
```yaml
sender: "sgibson@glasswallsolutions.com"
to: ["sgibson@glasswallsolutions.com"]
smtp_server: localhost
tenant_id: <guid>
port: 25
attach:
- "C:/path/to/an/attachment.pdf"
```

Where:
- `sender`: The email address sending the email.
- `to`: The list of emails to send the email to.
- `smtp_server`: The SMTP server to send the email to.
- `tenant_id`: The FileTrust tenant ID to send the email with.
- `port`: The port on the SMTP server to connect via.
- `attach`: The list of files to attach.

If that manifest YAML file was `localhost.yml`, then to send it you would run:
```
$ victoria email send localhost.yml
```

#### Replaying dead letters
The `replay` command is used for replaying dead letters.

Simply run it with a cluster name and it will scan for dead letters in the queues
and replay them.

Example:
```
$ victoria email replay uksprod1
```

Will replay dead letters using the service bus connection string under key `uksprod1`
in the config file's `service_bus_connection_strings` section.

The queues it scans can be modified by editiing the config file's `queues` section.

#### Reconstructing mail
The `reconstruct` command can be used to reconstruct emails to files from transaction IDs.
It can also scan dead letter queues and reconstruct mail from the dead lettered transactions.

It can also optionally anonymise the email contents if you need to give the email
to a developer for them to help identify an issue.

Example of reconstructing mail with a transaction ID:
```
$ victoria email reconstruct uksprod1 -i <guid> -o output_folder
```

Example of reconstructing and anonymising mail:
```
$ victoria email reconstruct useprod3 -i <guid> -o output_folder --anon
```

Example of reconstructing multiple transactions:
```
$ victoria email reconstruct uksprod2 -i <guid1> -i <guid2> -i <guid3> -o output_folder
```

Example of reconstructing mail from service bus dead letters:
```
$ victoria email reconstruct useprod4 -o output_folder
```

The cluster name given corresponds to keys in both `service_bus_connection_strings`
and `storage_accounts` in the config.

#### Replaying mail through the system
The `recover` command can replay mail through the system right from the beginning.
It does this by using a transaction ID to grab the failed mail, reconstructing it,
and sending it to an SMTP endpoint, as if it were a new mail.

This should only be done in the event of an emergency (mostly when SMTP receiver
was not able to put a received email on the message inspection queue). If you
replay a message more than once or replay a message that has already been
transmitted then customers will receive duplicate emails.

It accepts a list of transaction IDs to replay in the form of a text file, with
each transaction ID on a separate line:
```
896551ff-520f-4055-8452-36b4de64f0b4
fd18b432-4307-4fbb-a7f6-e149bace0bae
52b4686b-0ac4-4b6a-b3e0-3a8f3db47711
...
```

For example, to replay those transactions in file `bad-tx.txt` (with SMTP Rx
port forwarded on port 25 via `kubectl`):
```
$ victoria email recover uksprod1 -i bad-tx.txt -o localhost:25
```

The cluster name given here corresponds to a key in `storage_accounts` in the
config.

## Developer guide

### Prerequisites
- Python 3.7+
- Pipenv

### Quick start
1. Clone this repo.
2. In the root of the repo, run `pipenv sync --dev`.
3. You're good to go. You can run the plugin during development with 
   `pipenv run victoria email`.