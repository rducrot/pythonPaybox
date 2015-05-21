#!/usr/bin/python
# -*- coding: iso8859-1 -*-
import settings
import binascii
import hashlib
import hmac
import urlparse
import os

class Transaction:
	"""A Paybox System transaction, from your server to the customer's browser, and from Paybox server to yours

	Attributes:
		MANDATORY	The values nedded to call for a payment
		ACCESSORY	The values you may add to modify Paybox behavior
		RESPONSE_CODES	Every response code Paybox may return after a payment attempt
	"""

	def __init__(self, production=False, PBX_TOTAL=None, PBX_CMD=None, PBX_PORTEUR=None, PBX_TIME=None, PBX_REPONDRE_A=None):
		self.production = production
		
		if self.production:
			self.action = 'https://tpeweb.paybox.com/cgi/MYchoix_pagepaiement.cgi'
			self.SECRET = settings.SECRETKEYPROD
		else:
			self.action = 'https://preprod-tpeweb.paybox.com/cgi/MYchoix_pagepaiement.cgi'
			self.SECRET = settings.SECRETKEYTEST
		
		self.MANDATORY = {
			'PBX_SITE': settings.PBX_SITE,			# SITE NUMBER (given by Paybox)
			'PBX_RANG': settings.PBX_RANG,			# RANG NUMBER (given by Paybox)
			'PBX_IDENTIFIANT': settings.PBX_IDENTIFIANT,	# IDENTIFIANT NUMBER (given by Paybox)
			'PBX_TOTAL': PBX_TOTAL,				# Total amount of the transaction, in cents
			'PBX_DEVISE': '',				# Currency of the transaction
			'PBX_CMD': PBX_CMD,				# Transaction reference generated by the ecommerce
			'PBX_PORTEUR': PBX_PORTEUR,			# Customer's email address
			'PBX_RETOUR': 'TO:M;RE:R;AU:A;RC:E;SIGN:K',	# List of the variables Paybox must return to the IPN url
			'PBX_HASH': 'SHA512',	# Hash algorithm used to calculate the Hmac value
			'PBX_TIME': PBX_TIME,	# Time of the transaction (iso 8601 format)
		}

		self.ACCESSORY = {
			'PBX_REFUSE': '',		# url de retour en cas de refus de paiement
			'PBX_REPONDRE_A': PBX_REPONDRE_A,		# url IPN. WARNING. With Trailing slash, otherwise Django 301 to it...
			'PBX_EFFECTUE': '',		# url de retour en cas de succes
			'PBX_ANNULE': '',		# url de retour en cas d'abandon
			'PBX_LANGUE': 'FRA', 		# 3 Chars. payment language. GBR for English
		}
		
		self.RESPONSE_CODES = {
			"00000": "Success",
			"00001": "Connection failed. Make a new attempt at tpeweb1.paybox.com",
			"001xx": "Payment rejected",
			"00003": "Paybox Error. Make a new attempt at tpeweb1.paybox.com",
			"00004": "Card Number invalid",
			"00006": "site, rang, or identifiant invalid. Connection rejected",
			"00008": "Card Expiration Date invalid",
			"00009": "Error while creating a subscription",
			"00010": "Unrecognized currency",
			"00011": "Incorrect amount",
			"00015": "Payment already done",
			"00016": "Subscriber already known",
			"00021": "Unauthorized Card",
			"00029": "Incorrect Card Number",
			"00030": "Time Out",
			"00031": "Reserved",
			"00032": "Reserved",
			"00033": "Country Not Supported",
			"00040": "3DSecure validation failed",
			"99999": "Payment on Hold",
		}


	def post_to_paybox(self):
		""" Returns three variables ready to be integrated in an hidden form, in a template
		"""
		self.MANDATORY['PBX_TIME'] = self.MANDATORY['PBX_TIME'].isoformat()
		
		# 978 = €
		self.MANDATORY['PBX_DEVISE'] = '978'

		# string to sign. Made of the Mandatory variables in a precise order.
		tosign = "PBX_SITE=%(PBX_SITE)s&PBX_RANG=%(PBX_RANG)s&PBX_IDENTIFIANT=%(PBX_IDENTIFIANT)s&PBX_TOTAL=%(PBX_TOTAL)s&PBX_DEVISE=%(PBX_DEVISE)s&PBX_CMD=%(PBX_CMD)s&PBX_PORTEUR=%(PBX_PORTEUR)s&PBX_RETOUR=%(PBX_RETOUR)s&PBX_HASH=%(PBX_HASH)s&PBX_TIME=%(PBX_TIME)s" % self.MANDATORY 

		# for the accessory variables, the order is not important
		for name, value in self.ACCESSORY.items():
			if value:
				tosign+=('&'+name+'='+value)

		binary_key = binascii.unhexlify(self.SECRET)
		signature = hmac.new(binary_key, tosign, hashlib.sha512).hexdigest().upper()
		self.MANDATORY['hmac'] = signature

		return {
			'action'   : self.action,
			'mandatory': self.MANDATORY,
			'accessory': self.ACCESSORY,
		}

	def construct_html_form(self, production=False):
		""" Returns an html form ready to be used (string)
		"""

		accessory_fields = '\n'.join(["<input type='hidden' name='{0}' value='{1}'>".format(field, self.ACCESSORY[field]) for field in self.ACCESSORY if self.ACCESSORY[field]])

		html = """<form method=POST action="{action}">
			<input type="hidden" name="PBX_SITE" value="{mandatory[PBX_SITE]}">
			<input type="hidden" name="PBX_RANG" value="{mandatory[PBX_RANG]}">
			<input type="hidden" name="PBX_IDENTIFIANT" value="{mandatory[PBX_IDENTIFIANT]}">
			<input type="hidden" name="PBX_TOTAL" value="{mandatory[PBX_TOTAL]}">
			<input type="hidden" name="PBX_DEVISE" value="{mandatory[PBX_DEVISE]}">
			<input type="hidden" name="PBX_CMD" value="{mandatory[PBX_CMD]}">
			<input type="hidden" name="PBX_PORTEUR" value="{mandatory[PBX_PORTEUR]}">
			<input type="hidden" name="PBX_RETOUR" value="{mandatory[PBX_RETOUR]}">
			<input type="hidden" name="PBX_HASH" value="{mandatory[PBX_HASH]}">
			<input type="hidden" name="PBX_TIME" value="{mandatory[PBX_TIME]}">
			<input type="hidden" name="PBX_HMAC" value="{mandatory[hmac]}">
			{accessory}
			<input type="submit" value="Payer">
		</form>"""

		return html.format(action=self.action, mandatory=self.MANDATORY, accessory=accessory_fields)

	def verify_notification(self, response_url, order_total, verify_certificate=True):
		""" Verifies the notification sent by Paybox to your server.
		
		It verifies :
			- the authenticity of the message
			- the fact that the message has not been altered
			- if not in production, the auth_number must be "XXXXXX"
			- if in production, there must be a Response Code
			- the total returned must be equal to the total of the order you've saved in ddb
		    
		:response_url: (string), the full response url with its encoded args
		:order_total': (int), the total amount required
		:verify_certificate: (bool)
		    
		It returns a dict which contains three variables:
			- success, (bool) True if the payment is valid
			- status, (str) The Paybox Response Code
			- auth_code, (str) The Authorization Code generated by the Authorization Center
		"""
		
		url_parsed = urlparse.urlparse(response_url) 	# object
		message = url_parsed.query			# string
		query = urlparse.parse_qs(message) 	 	# dictionnary

		if verify_certificate:
			self.verify_certificate(message=message, signature=query['SIGN'][0])
			
		if not self.production:
			assert query['AU'][0] == "XXXXXX", "Incorrect Test Authorization Code"
		else:
			assert 'RC' in query, "No Response Code Returned"
		
		assert query['TO'][0] == str(order_total), "Total does not match"

		return {
			'success': True if query['RC'][0] == "00000" else False,
			'status': self.RESPONSE_CODES.get(query['RC'][0][:-2] + 'xx', self.RESPONSE_CODES.get(query['RC'][0], "Unrecognized Response Code")),
			'auth_code': query['AU'][0] if query['AU'][0] else False,
		}

	def verify_certificate(self, message, signature):
		""" Verifies the Paybox certificate, authenticity and alteration.
		If everything goes well, returns True. Otherwise raise an Error
		
		:message: (str), the full url with its args
		:signature: (str), the signature of the message, separated from the url
		
		Flow:
			- The signature is decoded base64
			- The signature is removed from the message
			- The Paybox pubkey is loaded from an external file
			- it's validity is checked
			- The message is digested by SHA1
			- The SHA1 message is verified against the binary signature
		"""
		import base64
		import hashlib
		import M2Crypto as m2
	
		# detach the signature from the message 
		message_without_sign = message.split("&SIGN=")[0]
		# decode base64 the signature
		binary_signature = base64.b64decode(signature)
		# create a pubkey object
		pubkey = m2.RSA.load_pub_key(os.path.join(os.path.dirname(__file__), 'pubkey.pem'))
		# verify the key
		assert pubkey.check_key(), 'Key Verification Failed'
		# digest the message
		sha1_hash = hashlib.sha1(message_without_sign).digest()
		# and verify the signature
		assert pubkey.verify(data=sha1_hash, signature=binary_signature), 'Certificate Verification Failed'

		return True
