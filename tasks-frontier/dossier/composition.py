"""Orthogonal narrative composition: provenance, scope and exception overlays.

The same decisive legal phrases can appear in both live and rejected records.
These operators vary independently of the 24 legal-history families. None of
their private switches or generated answer fields is exported to the corpus.
"""
from authoring import EXCEPTIONS, story


def competing_copies(family,polarity,context,labels,mode):
    positive=story(family,True,context);negative=story(family,False,context)
    # Labels are independently shuffled random packet identifiers. Their
    # order and spelling carry no relationship to acceptance or rejection.
    active=labels[0] if polarity else labels[1]
    rejected=labels[1] if polarity else labels[0]
    scope=context['scope'];other=context['other_scope']
    combined=[]
    for left,right in zip(positive.text,negative.text):
        if left==right:combined.append(left)
        else:
            combined.append(f'The migrated archive contains two incompatible transcriptions of this record. Copy {labels[0]} reads: "{left}" Copy {labels[1]} reads: "{right}" These are alternate accounts of one event, not two new agreements. Use the custodian\'s source reconciliation for this service to identify the faithful copy; neither transcription is independently authoritative.')
    # A duplicate of a comparative record cannot reveal which version wins.
    combined[6]='Certified reproduction of the comparison record only; this certificate does not choose between its source copies: '+combined[2]
    if mode==0:
        choice=f'The jointly appointed archive custodian certified copy {active} for {scope}. Copy {rejected} belongs to {other}; it was attached here during migration in error. The certification applies to all differing passages in this packet, including execution and disposition. It establishes what the historical record said, without making a new agreement.'
    elif mode==1:
        choice=f'The custodian withdrew the attribution of copy {rejected} to this service. Of the two copies in this packet, only the other is certified as the faithful account for {scope}. The withdrawal corrects archive lineage, not the historic commercial terms. Apply it to every conflicting passage, not just the last quoted sentence.'
    elif mode==2:
        choice=f'The secretary recommended copy {rejected}. Under the parties\' archive protocol, that recommendation has no evidentiary authority. The jointly appointed custodian instead authenticated copy {active} for {scope}, including its signature history. The secretary acknowledged the decision without withdrawing the earlier recommendation from the archive.'
    else:
        choice=f'Both copies were retained. The parties excluded copy {rejected} from the certification for {scope}; the certification covers the one remaining copy, including every conflicting quoted paragraph. Retention is not endorsement. This archive correction does not change any execution, commencement or expiry date found in the authenticated account.'
    return combined,choice


def exception_rider(context,new_exception,applies,mode):
    scope=context['scope'];other=context['other_scope'];clause=EXCEPTIONS[new_exception]
    proposal=f'An exception-only rider applies to whichever obligation is established by the prior instruments. It replaces that obligation\'s exception, including an original "no exception" provision, with this clause: {clause} It does not select a disputed substantive rule, cure missing evidence, transfer a customer, or reset the date on which that rule began. The rider is fully signed; its territorial and product scope is defined by the accompanying accepted scope note.'
    chosen=scope if applies else other;excluded=other if applies else scope
    if mode==0:
        scope_note=f'The accepted scope note assigns this exception-only rider to {chosen}. It expressly excludes {excluded}. The working draft assigned it to both, but the parties struck that wording before signature. The accepted note and rider form one instrument, effective before the review date.'
    elif mode==1:
        scope_note=f'The two services discussed were {scope} and {other}. The parties signed the rider for both except {excluded}; exactly one service remains covered. An account-manager recap calls it a group-wide concession, but that recap is neither signed nor incorporated. The narrower signed scope governs as of the review date.'
    else:
        scope_note=f'A crossed-out line named {excluded}. In the clean countersigned scope note that line is replaced by {chosen}. Both signatories initialled the replacement before execution. The cross-out is part of the executed original, not an unaccepted redline. The exception-only rider was in force for that selected service by the review date.'
    return proposal,scope_note


def restyle(text,rng):
    # Meaning-preserving lexical variation. Scope/negation/authority operators
    # above, rather than these synonyms, create the combinatorial difficulty.
    replacements={
        'Both parties':('Each of the two parties','The two contracting parties'),
        'The parties':('The contracting parties','The parties to the agreement'),
        'original rule':('original obligation','master-schedule rule'),
        'replacement obligation':('substituted obligation','replacement commitment'),
        'operative date':('commencement date','date of contractual effect'),
        'later request':('subsequent request','newer negotiating request'),
        'does not':('does not','does not by itself'),
        'in the archive':('in the retained correspondence','in the documentary archive'),
    }
    for old,variants in replacements.items():
        if rng.random()<.45:text=text.replace(old,rng.choice(variants))
    return text
