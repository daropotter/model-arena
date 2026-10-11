"""Private semantic scenario library. Never copied to the agent's workspace.

The paired variants deliberately share vocabulary and policy values. A word
like 'approved', a document's date or a signature alone cannot select a rule.
See REVIEW.md for the human-readable truth table and review limitations.
"""
from dataclasses import dataclass


TOPICS = {
    'retention': [('retain-year', 'keep the records for one year'), ('retain-quarter', 'erase the records after one quarter'), ('retain-until-close', 'retain the records until the account closes'), ('retain-month', 'erase the records after one month')],
    'notification': [('notify-immediately', 'notify the customer immediately after confirmation'), ('notify-next-day', 'notify the customer by the next business day'), ('notify-after-triage', 'notify the customer only after triage concludes'), ('notify-weekly', 'include the incident in the weekly notification')],
    'residency': [('eu-only', 'process customer content only within the European Union'), ('uk-only', 'process customer content only within the United Kingdom'), ('eu-uk', 'process customer content in either the European Union or the United Kingdom'), ('customer-choice', 'use the processing location designated by the customer')],
    'audit': [('onsite-audit', 'permit an on-site audit by the customer'), ('report-only', 'supply the independent assurance report instead of an on-site audit'), ('remote-audit', 'permit an audit through a remote evidence session'), ('joint-audit', 'permit only a pooled audit shared with other customers')],
    'subprocessors': [('prior-consent', 'obtain written customer consent before appointing a subprocessor'), ('notice-and-veto', 'give advance notice and allow the customer to veto a subprocessor'), ('notice-only', 'give advance notice without a contractual veto'), ('listed-only', 'use only subprocessors already named in the executed schedule')],
    'training': [('no-training', 'exclude customer content from every model-training dataset'), ('opt-in-training', 'use customer content for training only after a separate opt-in'), ('aggregate-training', 'use only aggregated non-identifying content for training'), ('tenant-training', 'use customer content only to train that customer\'s isolated model')],
    'keys': [('customer-keys', 'use keys held exclusively by the customer'), ('provider-keys', 'use keys held exclusively by the provider'), ('dual-keys', 'require both parties to release a decryption key'), ('escrow-keys', 'place recovery keys with the agreed escrow custodian')],
    'support': [('business-hours', 'provide support during local business hours'), ('continuous-support', 'provide support at all hours including holidays'), ('critical-only', 'provide out-of-hours support only for critical incidents'), ('partner-support', 'route support through the named service partner')],
    'exit': [('portable-export', 'supply a portable export on termination'), ('assisted-exit', 'provide an assisted migration on termination'), ('read-only-exit', 'provide a read-only transition period on termination'), ('erase-on-exit', 'erase the workspace on termination without a transition service')],
    'deletion': [('delete-all', 'delete production and backup copies together'), ('backup-cycle', 'delete production copies first and backups in their normal cycle'), ('hold-copy', 'retain a sealed copy until the dispute is resolved'), ('certified-delete', 'delete all copies and deliver an independent destruction certificate')],
    'disclosure': [('consent-disclosure', 'obtain consent before disclosing customer information'), ('legal-demand', 'disclose customer information only in response to a binding legal demand'), ('notice-disclosure', 'notify the customer before a permitted disclosure'), ('no-voluntary', 'refuse all voluntary disclosures to third parties')],
    'availability': [('service-credit', 'provide service credits for a qualifying outage'), ('termination-right', 'allow termination for a qualifying outage'), ('remediation-only', 'provide a remediation plan without a monetary remedy'), ('refund-outage', 'refund the affected service period for a qualifying outage')],
}

EXCEPTIONS = {
    'none': 'There is no exception to the selected rule within this scope.',
    'legal-hold': 'Records under a documented legal hold are excluded until the hold is released.',
    'critical-incident': 'During a declared critical incident, the incident response agreement replaces this rule.',
    'trial-tenants': 'Trial tenants remain on the original master-agreement rule.',
    'sealed-archive': 'The sealed archive remains governed by the original master-agreement rule.',
    'customer-managed': 'Customer-managed installations remain on the original master-agreement rule.',
}

BASIS = {
    'executed-change': 'A change has met all execution and commencement requirements.',
    'baseline-controls': 'No applicable change displaced the master-agreement rule.',
    'condition-met': 'The documentary prerequisite to a conditional change is satisfied.',
    'condition-failed': 'The prerequisite is known not to be satisfied; the baseline continues.',
    'condition-unknown': 'The archive cannot establish whether a necessary prerequisite occurred.',
    'specific-prevails': 'An express priority rule preserves the narrower instrument.',
    'restored-baseline': 'An executed rescission or expiry restored the original rule.',
    'conflict-unresolved': 'Incompatible instruments have equal priority and no tie-breaker.',
    'scope-unknown': 'The missing operative scope prevents assignment of an otherwise signed term.',
    'future-change': 'The signed change has not commenced by the review date.',
    'identity-transfer': 'A completed novation transferred this obligation to another legal entity.',
    'correction-ratified': 'Both parties ratified a substantive correction to the operative text.',
    'incorporated-term': 'A signed instrument selects a term by reference to another document.',
    'survival-clause': 'An express survival provision keeps an earlier rule in force.',
}


@dataclass
class Story:
    text: list
    state: str
    value: int | None
    exception: str
    since: str
    basis: str
    required: list
    owner: str = 'original'


FAMILIES = (
    'execution', 'authority', 'condition', 'sunset', 'scope', 'priority',
    'conflict', 'missing-schedule', 'partial-assent', 'correction', 'novation',
    'rescission', 'silence', 'receipt', 'trial', 'conjunction', 'incorporation',
    'future', 'renewal', 'nested-exception', 'delegation', 'counteroffer',
    'survival', 'translation',
)


def story(family, polarity, c):
    """Eight linked records, plus master/identity records supplied by builder.

    Policy positions A/B/C are privately shuffled on every track. 'required'
    refers to records, not privileged labels in the public corpus.
    """
    a,b,d=c['terms']; ex=EXCEPTIONS[c['exception']]
    scope=c['scope']; other=c['other_scope']; x=c['instrument']; y=c['other_instrument']
    base=c['base_date']; start=c['start_date']; early=c['expiry_date']
    # Every record has a different purpose. The final proposal and operational
    # evidence are genuine tempting contradictions, not length padding.
    t=[
        f'For {scope}, instrument {x} would replace the existing obligation to {a} with an obligation to {b}. {ex} The proposal leaves the other service lines and territories untouched. Its operative date, if executed and commenced, is {start}.',
        '', '', '',
        f'The operations team currently configures {scope} to {d}. That configuration was selected for a rehearsal; the ticket does not certify that the contract permits it. Operations asks the contract desk to reconcile the setting with {x} before treating it as the live commitment.',
        f'A new commercial request asks that {scope} should instead {d}, removing the proposed exception. The sender calls this the preferred final position. This is a negotiating request, not an executed variation; neither party has supplied the acceptance required by the master agreement.',
        '',
        f'Archive reconciliation for {scope}: the working proposal {x}, correspondence about its authority and commencement, and the master schedule must be read together. The later request does not settle the earlier issue. The archive contains the complete execution correspondence except for omissions explicitly recorded in the evidence notes.',
    ]
    state='bound';value=1 if polarity else 0;exception=c['exception'] if polarity else 'none'
    since=start if polarity else base;basis='executed-change' if polarity else 'baseline-controls'
    owner='original';required=[0,1,2]
    if family=='execution':
        t[1]=f'The executed signature page refers to {x}. Both authorized officers signed the page, but the box immediately above their signatures limits what they sign: '+('the operative variation and its scope are approved.' if polarity else 'only the record of negotiations is approved; the operative variation is reserved.')
        t[2]='The filing clerk attached the page to the proposal without changing its contents. A signed record of negotiations is not execution of the terms described in those negotiations.'
        t[3]='No second signature page, acceptance email or subsequent activation instrument appears in the complete correspondence register.'
    elif family=='authority':
        t[1]=f'The message says: "Approved in full, including the exception, for {x}." It is sent by Morgan Vale, described in the mail footer as delivery director. The counterparty accepted the same text.'
        t[2]='The delegation register distinguishes operational approval from contractual authority. For this signature window Morgan '+('held a countersigned delegation to vary this topic for this scope.' if polarity else 'could authorize deployments only; contractual variations were reserved to the two signatories named in the master.')
        t[3]='The named master signatories did not send a separate ratification. The delegation register, rather than the sender\'s job title or the word "Approved", determines whether the email executed a change.'
    elif family=='condition':
        t[1]=f'Both parties executed {x}, but its commencement clause says the variation starts only once the receiving party acknowledges the independent acceptance certificate. Until then the original term remains binding.'
        t[2]='The certificate is complete. The transmission ledger '+('contains the receiving party\'s acknowledgment of that certificate, dated before the operative date.' if polarity else 'records delivery failure and confirms that the receiving party had not acknowledged the certificate by the review date.')
        t[3]='A later operations note says "ready for launch". That phrase reports technical readiness only; it neither acknowledges the certificate nor waives the contractual prerequisite.'
        basis='condition-met' if polarity else 'condition-failed'
    elif family=='sunset':
        t[1]=f'Both authorized parties executed {x}. Its term is temporary and the master rule automatically resumes at sunset, without a fresh signature.'
        t[2]=f'The commencement certificate sets the sunset to '+('2027-02-01.' if polarity else early+'.')+' No extension was executed. An internal reminder asks for an extension but does not grant one.'
        t[3]='The temporary exception has exactly the same lifetime as the temporary replacement rule. It does not survive restoration of the master schedule.'
        if not polarity: basis='restored-baseline';since=early
    elif family=='scope':
        t[1]=f'Both officers signed {x}; the signature is unconditional. Two service descriptions were discussed: {scope} and {other}.'
        t[2]='The accepted scope is described by exclusion: '+(f'the latter service is excluded; the former remains covered.' if polarity else f'the former service is excluded; the latter remains covered.')+' The rejected redline had the opposite exclusion.'
        t[3]='The clean schedule incorporates the accepted exclusion, not the rejected redline. Shared hosting and similar product names do not extend the change to the excluded service.'
    elif family=='priority':
        t[1]=f'Instrument {x} was executed for {scope}. A later general instrument {y} says to {d} for every service and does not repeat the exception.'
        t[2]='The later instrument explicitly '+('preserves earlier service-specific schedules, which prevail over its general terms.' if polarity else 'replaces earlier service-specific schedules, even where those schedules were narrower.')
        t[3]=f'Both instruments were executed by authorized officers. The general instrument commenced on {early}. Neither document has a later withdrawal or a different priority clause.'
        basis='specific-prevails' if polarity else 'executed-change'
        if not polarity:value=2;since=early
    elif family=='conflict':
        t[1]=f'Two original instruments were signed at the same meeting for {scope}. One requires parties to {b}; the other requires parties to {d}. Their stated operative dates are identical. The first contains this exception: {ex}'
        t[2]=('The jointly signed order-of-precedence sheet says that the instrument with the exception prevails for this service.' if polarity else 'The order-of-precedence sheet is absent. Neither original gives itself priority, and both signatures are valid. The parties have recorded that they cannot agree which text controls.')
        t[3]='Later upload timestamps reflect scanning order, not execution order. A filing clerk cannot choose between inconsistent obligations. No rescission or settlement follows in the closed register.'
        if not polarity:state='unresolved';value=None;exception='?';since='?';basis='conflict-unresolved'
    elif family=='missing-schedule':
        t[1]=f'The signed variation {x} assigns the replacement rule only to the service specified in its incorporated scope sheet. The body discusses {scope} and {other}, but deliberately does not select either.'
        t[2]=(f'The certified scope sheet names {scope}, excludes {other}, and is countersigned by both parties.' if polarity else 'The archive export omitted the scope sheet. The custodian confirms that it could have named either service and cannot reconstruct its contents from the surviving file names.')
        t[3]='There is no default scope for a missing incorporated sheet. It would be equally unsupported to assume that the variation applied everywhere or nowhere.'
        if not polarity:state='unresolved';value=None;exception='?';since='?';basis='scope-unknown'
    elif family=='partial-assent':
        t[1]=f'The email accepting the packet for {x} lists two paragraphs: paragraph one is the replacement obligation and exception; paragraph two is an administrative billing-contact change.'
        t[2]='The recipient writes: '+('"We accept paragraph one. Please leave paragraph two open."' if polarity else '"We accept paragraph two. Please leave paragraph one open."')+' The sender agrees to implement exactly the accepted paragraph and not the outstanding one.'
        t[3]='The master permits separately accepted paragraphs to operate independently. Agreement about the billing contact cannot execute the substantive obligation by implication.'
    elif family=='correction':
        t[1]=f'The executed master still says to {a}. A document headed "clerical correction" would replace that text with {b} and add the exception. The document would materially change what must be done.'
        t[2]=('Both authorized parties countersigned the correction as a substantive variation, effective on the proposed operative date.' if polarity else 'Only the scanning vendor signed the correction. Both parties acknowledged receipt but expressly withheld approval of any substantive variation.')
        t[3]='The word "correction" in the title does not itself amend a contract. The scanned master has no illegible word at the disputed clause; the disagreement is about substance, not image quality.'
        if polarity:basis='correction-ratified'
    elif family=='novation':
        t[1]=f'The parties agreed the replacement term and exception in {x}. In the same packet they proposed transferring the customer\'s entire contractual position, including its right to receive this performance and its corresponding liabilities, to legal entity {c["successor"]}. The predecessor remains the customer until the novation has all three consents.'
        t[2]='The proposed successor and predecessor signed the transfer. The service provider '+('consented to the novation and released the predecessor on the operative date.' if polarity else 'consented to the replacement term but refused the novation and did not release the predecessor.')
        t[3]='The replacement term is expressly severable from the transfer. A new trading name or a shared billing address cannot substitute for the provider\'s consent to release the old legal entity.'
        value=1;exception=c['exception'];since=start;owner='successor' if polarity else 'original';basis='identity-transfer' if polarity else 'executed-change'
    elif family=='rescission':
        t[1]=f'Both parties executed {x}, including its exception. A later rescission packet proposed restoring the original rule for {scope}.'
        t[2]='The final countersigned page '+('rejects the rescission and reaffirms the variation.' if polarity else 'accepts the rescission, restoring the original rule and removing the exception.')
        t[3]=f'The disposition is effective on {early}. Rejected text remains in the packet as an exhibit; it does not have operative force merely because the exhibit was uploaded last.'
        if not polarity:basis='restored-baseline';since=early
    elif family=='silence':
        t[1]=f'The sender asks for objections to {x}. The recipient does not object. The master normally requires express acceptance, but the parties may execute a topic-specific silence procedure in advance.'
        t[2]=('Both parties had executed that procedure for precisely this topic and service. Its notice period ended without objection before the operative date.' if polarity else 'The only silence procedure was an unsigned draft for a different topic. No executed exception displaced the master\'s express-acceptance requirement here.')
        t[3]='"No objection" and "accepted" are therefore not interchangeable without reading the earlier procedure. The complete notice register contains no timely objection or express later acceptance.'
    elif family=='receipt':
        t[1]=f'The sender transmitted {x}; a response headed "Accepted" arrived. The body distinguishes acceptance into the document store from acceptance of the legal terms.'
        t[2]=('The authorized recipient states that both meanings apply: the packet is stored and the replacement obligation with its exception is accepted.' if polarity else 'The authorized recipient states that only storage is accepted: legal review remains open and no obligation or exception is agreed.')
        t[3]='The sender agrees that only the expressly accepted meaning is effective. A delivery-status label or subject line cannot expand the text of the reply.'
    elif family=='trial':
        t[1]=f'The variation {x} was executed. Its scope uses the internal term "release lane", which the signed definitions map either to production or to trials. The query concerns production service.'
        t[2]='The incorporated definitions say that for this packet "release lane" means '+('production tenants, and expressly excludes trial tenants.' if polarity else 'trial tenants, and expressly excludes production tenants.')
        t[3]='The proposed rule and exception do not cross between those populations. An internal deployment ticket reused the phrase for both populations; the signed definition controls.'
    elif family=='conjunction':
        t[1]=f'The parties signed {x} subject to two cumulative conditions: the independent certificate must be acknowledged AND the customer\'s risk officer must approve deployment. One is not a substitute for the other.'
        t[2]='The certificate was acknowledged. '+('The risk officer also signed the required approval, with both events before commencement.' if polarity else 'The export contains neither the risk officer\'s decision nor a rejection. The custodian confirms that this correspondence channel is missing from the archive.')
        t[3]='A project-manager email says "approved" but explicitly refers to the certificate alone. The risk decision cannot be inferred from it, and the signed change has no waiver of that second condition.'
        basis='condition-met' if polarity else 'condition-unknown'
        if not polarity:state='unresolved';value=None;exception='?';since='?'
    elif family=='incorporation':
        t[1]=f'The working annex presents two alternatives. The first says to {b} and includes the exception. The second says to {d} without that exception. Neither alternative is binding just because it appears in the annex.'
        t[2]='The executed selection letter incorporates '+('the first alternative and rejects the second.' if polarity else 'the second alternative and rejects the first.')+' It incorporates the selected alternative\'s associated exception wording as well.'
        t[3]=f'The selection letter and working annex together form the instrument commencing on {start}. The unselected text is retained solely to explain the negotiation.'
        basis='incorporated-term';value=1 if polarity else 2;since=start
    elif family=='future':
        t[1]=f'The parties signed {x}. Signature and commencement are separate events under this packet; neither the filing date nor an early technical deployment advances commencement.'
        t[2]='The commencement clause sets the date to '+(start if polarity else '2026-11-15')+'. No acceleration agreement was executed. The exception starts together with the replacement obligation.'
        t[3]='An operations email says "already implemented" but reports a staging deployment. The master remains binding up to the contractual commencement date.'
        if not polarity:basis='future-change'
    elif family=='renewal':
        t[1]=f'Both parties signed {x}. A later renewal summarizes the baseline obligation to {a} and omits the exception from its summary.'
        t[2]='The renewal\'s operative integration clause '+('preserves all executed variations despite omissions from its non-exhaustive summary.' if polarity else 'replaces all previous variations; only terms repeated in the renewal survive.')
        t[3]=f'The renewal commenced on {early}. The summary is not independently signed as a variation. Its effect depends on the integration clause, not on which paragraph contains the last policy phrase.'
        basis='survival-clause' if polarity else 'restored-baseline'
        if not polarity:since=early
    elif family=='nested-exception':
        t[1]=f'The replacement term in {x} was signed for all services except {other}. A rider then addresses an exclusion from that exclusion.'
        t[2]=('The rider confirms that the query service was never in the excluded class, so the replacement term and its stated exception apply.' if polarity else f'The rider identifies {scope} as belonging to the excluded class, despite its similar commercial name. The purported exclusion from the exclusion covers a different deployment only.')
        t[3]='Commercial names are not scope definitions. The parties countersigned the rider and made it part of the variation. No later document broadens its reinstatement provision.'
    elif family=='delegation':
        t[1]=f'An agent accepted {x} on behalf of the customer. A delegation signed before the acceptance covered this exact topic, territory and product.'
        t[2]='The revocation register shows '+('that the delegation was revoked only after the acceptance; the revocation expressly leaves prior executed acts intact.' if polarity else 'that the delegation was revoked before the acceptance; the agent had received notice and could no longer bind the customer.')
        t[3]='The counterparty did not rely on apparent authority and expressly required actual delegation. There was no later ratification. Ordering the revocation against acceptance matters more than ordering upload timestamps.'
    elif family=='counteroffer':
        t[1]=f'The response to {x} says "We accept, subject to retaining the master rule instead of the replacement rule." The master treats a substantive reservation as a counteroffer, not acceptance.'
        t[2]=('The recipient then withdrew the reservation in an authorized message and accepted the original proposal including its exception.' if polarity else 'The reservation was never withdrawn. The proposing party rejected it, and the exchange ended without agreement.')
        t[3]='An internal sales note describes the negotiation as "accepted". It was written before legal review and is not a communication executing terms between the parties.'
    elif family=='survival':
        t[1]=f'The executed change {x} included a survival provision. The main service was later terminated and a transition workspace continued under the same queried scope.'
        t[2]='For that transition workspace the survival provision '+('keeps the replacement obligation and its exception in force.' if polarity else 'restores the master obligation and does not preserve the exception.')
        t[3]=f'Termination took effect on {early}. A later invoice describes the service as closed; it does not resolve obligations expressly continuing in the transition workspace.'
        basis='survival-clause';since=start if polarity else early
    elif family=='translation':
        t[1]=f'Two language versions were executed together. The English page says to {b} with the stated exception. The parallel page is rendered in the archive as requiring parties to {d}, without that exception.'
        t[2]='The bilingual execution clause gives priority to '+('the English page when the two versions differ.' if polarity else 'the parallel page when the two versions differ.')+' The archive translation is certified by both parties; its meaning is not disputed.'
        t[3]=f'Both pages commence on {start}. Page order in the scanned PDF is an export artifact. The lower-priority page remains in the archive but cannot supply a different binding obligation.'
        value=1 if polarity else 2;since=start;basis='specific-prevails'
    else:
        raise ValueError(family)
    if family in ('authority','delegation','rescission','priority','renewal','survival'):
        required.append(3)
    # Separate certified extract is an acceptable alternate source for the
    # dispositive p2, but does not certify omitted authority/scope evidence.
    t[6]='The parties certified this extract as a faithful duplicate of the disposition record, not as a new amendment: '+t[2]
    return Story(t,state,value,exception,since,basis,required,owner)
