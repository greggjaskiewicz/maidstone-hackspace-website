from pprint import pprint
import pytz
import gocardless_pro as gocardless
import braintree
import logging

from django.conf import settings
payment_providers = settings.PAYMENT_PROVIDERS
logger = logging.getLogger(__name__)
# import paypalrestsdk as paypal

PROVIDER_ID = {'gocardless':1, 'braintree': 2}
PROVIDER_NAME = {1: 'gocardless', 2: 'braintree'}

def select_provider(type):
    if type == "gocardless": return gocardless_provider()
    if type == "braintree": return braintree_provider()
    if type == "paypal": return paypal_provider()

    log.exception('[scaffold] - "No Provider for ' + type)
    assert 0, "No Provider for " + type

class gocardless_provider:
    """
    gocardless test account details 20-00-00, 55779911
    """
    form_remote = True
    client = None

    def __init__(self):
        # gocardless are changing there api, not sure if we can switch yet
        self.client = gocardless.Client(
            access_token=payment_providers['gocardless']['credentials']['access_token'],
            environment=payment_providers['gocardless']['environment'])

    def subscribe_confirm(self, args):
        response = gocardless.client.confirm_resource(args)
        subscription = gocardless.client.subscription(args.get('resource_id'))
        return {
            'amount': subscription.amount,
            'start_date': subscription.created_at,
            'reference': subscription.id,
            'success': response.success
        }

    def fetch_customers(self):
        """Fetch list of customers payments"""
        for customer in self.client.customers.list().records:
            for payment in self.client.payments.list(params={"customer": customer.id}).records:
                yield {
                    'user_reference': customer.id,
                    'email': customer.email,
                    'status': payment.status,
                    'payment_id': payment.links.subscription,
                    'payment_type': 'subscription' if payment.links.subscription else 'payment',
                    'payment_date': payment.created_at,
                    'amount': payment.amount
                }


    def fetch_subscriptions(self):
        # for paying_member in self.client.mandates.list().records:
        for paying_member in self.client.subscriptions.list().records:
            mandate=self.client.mandates.get(paying_member.links.mandate)
            user=self.client.customers.get(mandate.links.customer)

            # gocardless does not have a reference so we use the id instead
            yield {
                'status': paying_member.status,
                'email': user.email,
                'start_date': paying_member.created_at,
                'reference': mandate.id,
                'amount': paying_member.amount}

    def get_redirect_url(self):
        return payment_providers['gocardless']['redirect_url']

    def get_token(self):
        return 'N/A'

    def cancel_subscription(self, reference):
        try:
            subscription = gocardless.client.subscription(reference)
            response = subscription.cancel()
        except  gocardless.exceptions.ClientError:
            return {
                'success': False
            }
        return {
            'amount': subscription.amount,
            'start_date': subscription.created_at,
            'reference': subscription.id,
            'success': response.get('success', False)
        }

    def create_subscription(self, user, session, amount,
                            name, redirect_success, redirect_failure,
                            interval_unit='monthly', interval_length='1'):
        return self.client.redirect_flows.create(params={
            "description": name,
            "session_token": session,
            "success_redirect_url": redirect_success,
            "prefilled_customer": {
                "given_name": user.first_name,
                "family_name": user.last_name,
                "email": user.email
            }
        })


    def confirm_subscription(self, membership, session, provider_response,
                             name, interval_unit='monthly', interval_length='1'):
        r = provider_response.get('redirect_flow_id')

        # response = self.client.redirect_flows.complete(r, params={
        #     "session_token": session
        # })
        response = self.client.redirect_flows.get(r)
        # response = self.client.redirect_flows.get(provider_response.get('redirect_flow_id'))

        # response = gocardless.client.confirm_resource(provider_response)
        # subscription = gocardless.client.subscription(provider_response.get('resource_id'))
        user_id = response.links.customer
        mandate_id = response.links.mandate
        # user = subscription.user()
        user = self.client.customers.get(response.links.customer)
        mandate = self.client.mandates.get(response.links.mandate)
        logging.debug(user)
        logging.debug(mandate)

        #  for some reason go cardless is in pence, so 20.00 needs to be sent as 2000
        #  what genious decided that was a good idea, now looks like i am charging £2000 :p
        #  the return is the same so you need to convert on send and receive
        subscription_response = self.client.subscriptions.create(
            params={
                'amount': str(membership.payment).replace('.', ''),
                'currency': 'GBP',
                'interval_unit': interval_unit,
                'name': name,
                # 'metadata': {'reference': },
                'links': {'mandate': mandate_id}
            })
        return {
            'amount': membership.payment,
            'email': user.email,
            'start_date': subscription_response.created_at,
            'reference': mandate_id,
            'success': subscription_response.api_response.status_code
        }


class braintree_provider:
    form_remote = False

    def __init__(self):
        braintree.Configuration.configure(
            environment=braintree.Environment.Sandbox,
            merchant_id=payment_providers['braintree']['credentials']['merchant_id'],
            public_key=payment_providers['braintree']['credentials']['public_key'],
            private_key=payment_providers['braintree']['credentials']['private_key'])

    def get_token(self):
        return braintree.ClientToken.generate()


    def create_subscription(self, amount, name, redirect_success, redirect_failure, interval_unit='month', interval_length='1'):
        result = braintree.Customer.create({
            "first_name": "test",
            "last_name": "user",
            "payment_method_nonce": nonce_from_the_client
        })

        return braintree.Subscription.create({
            "payment_method_token": "the_token",
            "plan_id": "membership",
            "merchant_account_id": "gbp_sandbox"
            #"price": "20.00"
            #'name': name
        })

    def confirm_subscription(self, args):
        if self.provider == 'gocardless':
            response = gocardless.client.confirm_resource(args)
            subscription = gocardless.client.subscription(args.get('resource_id'))
            return {
                'amount': subscription.amount,
                'start_date': subscription.created_at,
                'reference': subscription.id
            }


    def fetch_subscriptions(self):
        for paying_member in braintree.Subscription.search(braintree.SubscriptionSearch.status == braintree.Subscription.Status.Active):
            user=paying_member.user()
            yield {
                'status': paying_member.status,
                'email': user.email,
                'start_date': paying_member.created_at,
                'reference': paying_member.reference,
                'amount': paying_member.amount}


class payment:
    """
    https://developer.gocardless.com/api-reference/#redirect-flows-create-a-redirect-flow
    paypal reference = https://github.com/paypal/PayPal-Python-SDK
    gocardless reference = https://github.com/paypal/PayPal-Python-SDK
    """
    #~ def __call__(self, **args):
        #~ return self

    def __init__(self, provider='gocardless', style='payment', mode='sandbox'):
        self.provider = provider
        self.environment = int(mode=='production')
        self.provider_id = PROVIDER_ID.get(provider)

        print(payment_providers)
        if provider == 'paypal':
            paypal.configure(**payment_providers[provider]['credentials'])
            return

        gocardless_pro.Client(
            access_token=payment_providers[provider]['credentials']['access_token'],
            environment=payment_providers[provider])
        #~ environment = int('production' = payment_providers[provider]['environment'])
        gocardless.environment = payment_providers[provider]['environment']
        gocardless.set_details(**payment_providers[provider]['credentials'])
        merchant = gocardless.client.merchant()

    def lookup_provider_by_id(self, provider_id):
        return PROVIDER_NAME.get(provider_id, None)

    def make_donation(self, amount, reference, redirect_success, redirect_failure):
        if self.provider == 'paypal':
            payment = paypal.Payment({
                "intent": "sale",
                "payer": {"payment_method": "paypal"},
                "redirect_urls": {
                    "return_url": redirect_success,
                    "cancel_url": redirect_failure},

                "transactions": [{
                    "amount": {
                        "total": amount,
                        "currency": "GBP"},
                    "description": reference}]})

            payment_response = payment.create()
            print('payment create')
            if payment_response:
                print(payment_response)
                for link in payment.links:
                    if link.method == "REDIRECT":
                        redirect_url = str(link.href)
                        print(redirect_url)
                        return str(redirect_url)
            else:
                print("Error while creating payment:")
                print(payment.error)

        if self.provider == 'gocardless':
            return gocardless.client.new_bill_url(
                float(amount),
                name=reference,
                redirect_uri=redirect_success)

        return 'Error something went wrong'

    def fetch_subscriptions(self):
        if self.provider == 'gocardless':
            merchant = gocardless.client.merchant()
            for paying_member in merchant.subscriptions():
                user=paying_member.user()
                print(dir(paying_member)) 
                print(paying_member.next_interval_start) 
                print(paying_member.status) 
                print(dir(paying_member.user())) 
                yield {
                    'email': user.email,
                    'start_date': paying_member.created_at,
                    'reference': paying_member.id,
                    'amount': paying_member.amount}


    def confirm_subscription(self, args):
        if self.provider == 'gocardless':
            response = gocardless.client.confirm_resource(args)
            subscription = gocardless.client.subscription(args.get('resource_id'))
            return {
                'amount': subscription.amount,
                'start_date': subscription.created_at,
                'reference': subscription.id
            }

        if self.provider == 'paypal':
            print('subscribe_confirm')
            payment_token = args.get('token', '')
            billing_agreement_response = paypal.BillingAgreement.execute(payment_token)
            amount = 0
            print(billing_agreement_response)
            print(billing_agreement_response.id)
            for row in billing_agreement_response.plan.payment_definitions:
                amount = row.amount.value

            return {
                'amount': amount,
                'start_date': billing_agreement_response.start_date,
                'reference': billing_agreement_response.id
            }

        return None

    def unsubscribe(self, reference):
        if self.provider == 'gocardless':
            print('unsubscribe gocardless')
            subscription = gocardless.client.subscription(reference)
            print(subscription.cancel())

        if self.provider == 'paypal':
            # this may be wrong
            # ManageRecurringPaymentsProfileStatus 
            print(reference)
            billing_plan = paypal.BillingAgreement.find(reference)
            print(billing_plan)
            print(billing_plan.error)
            #~ billing_plan.replace([{"op": "replace","path": "/","value": {"state":"DELETED"}}])
            print(billing_plan.error)
            #~ invoice = paypal.Invoice.find(reference)
            options = {
                "subject": "Cancelling membership",
                "note": "Canceling invoice",
                "send_to_merchant": True,
                "send_to_payer": True
            }

            if billing_plan.cancel(options):  # return True or False
                print("Invoice[%s] cancel successfully" % (invoice.id))
            else:
                print(billing_plan.error)


    def subscribe(self, amount, name, redirect_success, redirect_failure, interval_unit='month', interval_length='1'):
        if self.provider == 'gocardless':
            return gocardless.client.new_subscription_url(
                amount=float(amount), 
                interval_length=interval_length, 
                interval_unit=interval_unit,
                name=name,
                redirect_uri=redirect_success)

        if self.provider == 'paypal':
            billing_plan = paypal.BillingPlan({
                "name": name,
                "description": "Membership subscription",
                "merchant_preferences": {
                    "auto_bill_amount": "yes",
                    "cancel_url": redirect_failure,
                    "initial_fail_amount_action": "continue",
                    "max_fail_attempts": "1",
                    "return_url": redirect_success,
                    "setup_fee": {
                        "currency": "GBP",
                        "value": amount
                    }
                },
                "payment_definitions": [{
                        "amount": {
                            "currency": "GBP",
                            "value": amount
                        },
                        "cycles": "0",
                        "frequency": interval_unit,
                        "frequency_interval": interval_length,
                        "name": "Regular 1",
                        "type": "REGULAR"
                    }
                ],
                "type": "INFINITE"
            })
            print('create bill')
            
            response = billing_plan.create()
            
            billing_plan = paypal.BillingPlan.find(billing_plan.id)
            
            if billing_plan.activate():
                start_date = datetime.utcnow() + timedelta(minutes=10)
                billing_agreement = paypal.BillingAgreement({
                    "name": billing_plan.name,
                    "description": name,
                    "start_date": start_date.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    "plan": {"id": str(billing_plan.id)},
                    "payer": {"payment_method": "paypal"}
                })
                
                if billing_agreement.create():
                    print('billing agreement id')
                    print(billing_agreement.id)
                    
                    for link in billing_agreement.links:
                        if link.rel == "approval_url":
                            approval_url = link.href
                            return approval_url
                else:
                    print(billing_agreement.error)
                    print('failed')

    def confirm(self, args):
        confirm_details = {}
        confirm_details['successfull'] = False
        print('---------------------')
        print(args)

        from pprint import pprint
        if self.provider == 'paypal':
            print(args.get('paymentId'))
            print(args.get('PayerID'))
            payment = paypal.Payment.find(args.get('paymentId'))
            pprint(payment)
            print(pprint(payment))
            print(payment)
            
            confirm_details['name'] = payment['payer']['payer_info'].first_name + ' ' + payment['payer']['payer_info'].last_name
            confirm_details['user'] = payment['payer']['payer_info'].email
            confirm_details['status'] = payment.state
            confirm_details['amount'] = payment['transactions'][0]['amount'].total
            confirm_details['created'] = payment.create_time
            confirm_details['reference'] = payment.id
            pprint(confirm_details)
            
            
            if payment.execute({"payer_id": args.get('PayerID')}):  # return True or False
                confirm_details['successfull'] = True
                print("Payment[%s] execute successfully" % (args.get('paymentId')))
            else:
                print(payment.error)
            return confirm_details

        if self.provider == 'gocardless':
            bill_id = args.get('resource_id')
            gocardless.client.confirm_resource(args)
            if bill_id:
                bill = gocardless.client.bill(bill_id)
                confirm_details['name'] = bill.name
                confirm_details['user'] = bill.user
                confirm_details['status'] = bill.status
                confirm_details['amount'] = bill.amount
                #~ confirm_details['amount_minus_fees'] = bill.amount_minus_fees
                confirm_details['created'] = bill.created_at
                confirm_details['reference'] = bill_id
                confirm_details['successfull'] = True
                return confirm_details
        return None
