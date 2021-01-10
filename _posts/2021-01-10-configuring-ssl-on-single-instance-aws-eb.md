---
layout: post
title:  "Configuring SSL on single instance AWS EB"
date: 2020-01-10 09:11:27 -0600
categories: aws, ssl, python, planet-tracker
---

Find the code for this post [here](https://gitlab.com/dean-shaff/eb-single-instance-ssl-config)

I’ve been running my Planet Tracker app on Heroku for a long time. This mostly due to the fact that deploying apps on Heroku (provided you don’t have system level dependencies) is dead easy. You can even set it up to run automatically after your Github CI pipeline finishes *with no additional configuration* -- you simply click a button on the dashboard for your app, and pow! it’s deployed. While I do actually use the app in the wild, it mostly serves as a sort of a sandbox for me to play around with novel web technologies. For instance, I originally put the client code together in vanilla JS, but I ended up moving to Vue.js in order to get some experience with the framework. On the backend, I’ve played around with web sockets and asynchronous Python code.

Given the prevalence of AWS products in the wild, I decided to try out redeploying my app using some combination of AWS products. I ended up using Elasticbeanstalk (EB), as it seemed closest to what I was doing with Heroku. I had a few goals for this redeployment project:

- Keep the price as close to $0/month as possible
- Gain some experience deploying web apps on AWS
- Speed up load times
- Use a custom domain, https://planet-tracker.com

With the AWS CLI client installed, getting my app set up with EB wasn’t super difficult. After getting things set up in EB, I purchased and registerd a domain with Route 53, and connected it to my EB environment. After about an hour of messing aroud, my app was running on my new domain. My app loaded wicked fast, sometimes two or three times faster than the Heroku version.

After the app was up for a month, I got a surprise in the form of a ~$25 bill from AWS. It turns out that the default EB environment uses a load balancer, which charges at minimum about $20 per month. Alarmed, I started looking for a cheaper solution. It turns out that you can shut down the load balancer, but then you lose SSL, meaning that your app won’t run over HTTPS.

Searching around online, I realized I had to rebuild my app as a single instance EB environment. This means that it would only run on one EC2 instance, instead of potentially splitting the load between multiple servers. This also meant that I would have to configure SSL on my own.

I’ve long been averse to messing around with more bare metal web app deployments, because it generally involves things like reverse proxies, which I consider myself completely unqualified to configure. That said, I found some relatively simple looking EB configurations I could apply to get things up and running. Unfortunately, all of the solutions I found didn’t work for me out of the box. Older solutions hinged on using versions of Linux that don’t run on newer EC2 instances, or employed extension configuration parameters that didn’t seem to work.

I'm going to walk through the configuration files from this [repo](https://gitlab.com/dean-shaff/eb-single-instance-ssl-config) (the same one I linked at the top of the post).

`.ebextensions/01_https.config`:

```
Resources:
  sslSecurityGroupIngress:
    Type: AWS::EC2::SecurityGroupIngress
    Properties:
      GroupId: {"Fn::GetAtt" : ["AWSEBSecurityGroup", "GroupId"]}
      IpProtocol: tcp
      ToPort: 443
      FromPort: 443
      CidrIp: 0.0.0.0/0

container_commands:
  00_install_epel:
    command: "sudo amazon-linux-extras install -y epel"
  01_install_certbot:
    command: "sudo yum install -y certbot"
  20_getcert:
    command: "sudo certbot certonly --standalone --debug --non-interactive --email dean.shaff@gmail.com --agree-tos --domains planet-tracker.com \
    --expand --renew-with-new-domains --pre-hook \"service nginx stop\""
  30_link:
    command: "sudo ln -sf /etc/letsencrypt/live/planet-tracker.com /etc/letsencrypt/live/ebcert"
  40_cronjobsetrenewal:
    command: '(crontab -l ; echo ''0 6 * * * root certbot renew --standalone --pre-hook "service nginx stop" --post-hook "service nginx start" --force-renew'') | crontab -'
```

These `.config` files, placed in the `.ebextensions` folder in the root of your project use YAML syntax. We can use them to do things like setting up new security rules and to run commands on our instance after we deploy. Walking through each section:

- `Resources`: This creates a new security rule for our instance, which allows ingress on port 443, for HTTPS. I copy and pasted this code from [this post](https://keithpblog.org/post/scaling-down-to-single-instance-elastic-beanstalk/).
- `container_commands`: This is a list of commands run before our app is deployed.
  - Notice that in the first two commands I'm installing `epel` and then `certbot`. Normally we'd do this in a separate `packages` section of the file, but I've found that we're not able to enable or install `amazon-linux-extras` packages in this section.
  - The third command gets the SSL (??) certificate using certbot.
  - The fourth command creates a symlink beween the newly created certificate and another location, which will be used in our nginx configuration.
  - The last command creates a cron job that will periodically renew our SSL certificate

(Note that if you were to use this with your own site, you'd have to modify all the occurences of `dean.shaff@gmail.com` and `planet-tracker.com` to your own email and domain, respectively.)

We have two more files, in `.platform/nginx/conf.d`: `000_http_redirect_custom.conf` and `https_custom.conf`. The structure of the `.platform` directory is deliberate: it tells EB to put those `.conf` files in `/etc/nginx/conf.d/` on the EC2 instance associated with our EB environment. These files allow us to modify our nginx (the public facing reverse proxy) configuration to allow HTTPS connections. I didn't write our modify these files, but the interesting bit is in the `.platform/nginx.conf.d/https_custom.conf` file:

```
server {
  listen       443 default ssl;
  server_name  localhost;
  error_page  497 https://$host$request_uri;

  ssl_certificate      /etc/letsencrypt/live/ebcert/fullchain.pem;
  ssl_certificate_key  /etc/letsencrypt/live/ebcert/privkey.pem;

  ssl_session_timeout  5m;
  ssl_protocols  TLSv1.1 TLSv1.2;
  ssl_ciphers "EECDH+AESGCM:EDH+AESGCM:AES256+EECDH:AES256+EDH";
  ssl_prefer_server_ciphers   on;

  location / {
    proxy_pass http://localhost:8000;
    proxy_http_version 1.1;

    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  }
}
```

In the `ssl_certificate` and `ssl_certificate_key` lines, we see that nginx is getting the SSL certificates we symlinked in the `container_commands` section of `01_https.config`!

For the sake of completeness, here's the contents of `.platform/nginx.conf.d/https_custom.conf/000_http_redirect_custom.conf`:

```
server {
  listen 80;
  return 301 https://$host$request_uri;
}
```

In the end, I was able to get my app running on `https://planet-tracker.com` (notice the "s" in "https"!), and I'm not incurring any more expenses than I was on Heroku. My very informal testing seems to indicate that my EB site doesn't load any faster than the Heroku version, however. Nonetheless, I gained some valuable experience playing around with AWS.

<!-- My purpose with this post was to document an up-to-date SSL configuration for a single instance AWS EB environment, not to do a comprehensive tutorial of setting up an Elasticbeanstalk instance for deploying simple Python applications. -->
