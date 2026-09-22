from enum import IntFlag

import comtypes.gen._C866CA3A_32F7_11D2_9602_00C04F8EE628_0_5_4 as __wrapper_module__
from comtypes.gen._C866CA3A_32F7_11D2_9602_00C04F8EE628_0_5_4 import (
    SpeechPropertyNormalConfidenceThreshold, ISpeechAudioBufferInfo,
    DISPID_SGRSTPropertyValue, DISPID_SLPsCount,
    DISPID_SRSetPropertyNumber, ISpRecognizer, SpVoice,
    SpeechCategoryAppLexicons, DISPID_SPPsItem, SPAS_RUN,
    DISPID_SPEDisplayAttributes, SAFT44kHz16BitStereo, VARIANT_BOOL,
    SAFT44kHz8BitMono, SVEAudioLevel, ISpeechLexiconWord,
    DISPID_SABIEventBias, DISPID_SOTCDefault, DISPID_SGRSTRule,
    IUnknown, SAFT11kHz8BitMono, DISPID_SLGetGenerationChange,
    DISPIDSPTSI_SelectionOffset, SPAUDIOSTATUS, SPRECORESULTTIMES,
    SAFT48kHz8BitStereo, SpeechVoiceCategoryTTSRate,
    DISPID_SVSInputWordLength, SAFTCCITT_uLaw_22kHzMono,
    SAFT24kHz16BitMono, DISPID_SLPLangId, eLEXTYPE_RESERVED8,
    eLEXTYPE_PRIVATE4, DISPID_SWFEBitsPerSample,
    DISPID_SAFSetWaveFormatEx, SVP_3, DISPID_SVEStreamEnd,
    SPSHORTCUTPAIR, SREFalseRecognition, DISPID_SPPName,
    DISPID_SPIGetText, eLEXTYPE_PRIVATE13, SAFTNonStandardFormat,
    SRSEIsSpeaking, SRAImport, DISPID_SRCEPropertyStringChange,
    DISPID_SPEsCount, SVP_6, DISPID_SGRSTsItem, DISPID_SAVolume,
    SSTTWildcard, SWPUnknownWordPronounceable,
    ISpeechPhraseReplacement, DISPID_SRCEFalseRecognition,
    SREHypothesis, SGLexicalNoSpecialChars, DISPID_SWFEChannels,
    DISPID_SRRTOffsetFromStart, SDTReplacement, DISPID_SVEWord,
    DISPID_SPRuleConfidence, SPPS_Noncontent, DISPID_SLPSymbolic,
    SPXRO_Alternates_SML, SPAR_Low, SPVOICESTATUS,
    DISPID_SOTGetDescription, SREPhraseStart, SVSFPersistXML,
    SAFT12kHz8BitMono, DISPID_SOTCEnumerateTokens, SRERecognition,
    DISPID_SLWs_NewEnum, DISPID_SGRSTPropertyId,
    DISPID_SLAddPronunciationByPhoneIds,
    DISPID_SPIAudioStreamPosition, ISpeechPhraseInfo,
    DISPIDSPTSI_SelectionLength, SPEI_RECO_STATE_CHANGE, SVP_21,
    SPDKL_LocalMachine, DISPID_SPRDisplayAttributes,
    DISPID_SRCCmdMaxAlternates, DISPID_SPEAudioSizeTime,
    Speech_Max_Word_Length, SPWORDLIST, SpeechTokenKeyFiles,
    DISPID_SVEBookmark, SVEAllEvents, SpeechCategoryRecoProfiles,
    SGLexical, DISPID_SDKGetBinaryValue, SPCT_SUB_COMMAND, HRESULT,
    SPSUnknown, DISPID_SPRs_NewEnum, DISPID_SRGetPropertyNumber,
    DISPID_SVPause, DISPID_SRGetRecognizers, ISpEventSource,
    SECFIgnoreKanaType, DISPID_SRCPause, SAFTGSM610_44kHzMono,
    DISPID_SLPsItem, SPSModifier, SPAUDIOBUFFERINFO, ISpRecoContext2,
    SPEI_RECOGNITION, DISPID_SRSSupportedLanguages, SRATopLevel,
    SRSInactiveWithPurge, SPWF_INPUT, DISPID_SRCRecognizer,
    DISPID_SRGRecoContext, ISpResourceManager, ISpRecoGrammar2,
    SAFTDefault, ISpeechLexiconPronunciations, eLEXTYPE_PRIVATE7,
    SPSMF_SRGS_SEMANTICINTERPRETATION_W3C, DISPID_SPRNumberOfElements,
    ISpRecoCategory, SPEI_VOICE_CHANGE, SECFEmulateResult,
    DISPID_SPPParent, SECFDefault, SRTExtendableParse,
    SECHighConfidence, ISpStreamFormatConverter, ISpeechMMSysAudio,
    ISpeechAudioStatus, DISPID_SPIRule, SVSFNLPSpeakPunc,
    DISPID_SPCIdToPhone, SAFTNoAssignedFormat, DISPID_SRGId, dispid,
    SAFTCCITT_uLaw_11kHzMono, eLEXTYPE_PRIVATE8, SPVPRI_OVER,
    DISPID_SRCState, SVP_9, SDKLLocalMachine, SP_VISEME_4,
    DISPID_SRCEInterference, DISPID_SPRuleChildren,
    ISpeechVoiceStatus, GUID, SDTAll, SpeechMicTraining,
    ISpGrammarBuilder, DISPID_SGRsCommit, DISPID_SRGCmdSetRuleIdState,
    DISPID_SGRSTNextState, DISPID_SRGCmdLoadFromObject,
    SAFTCCITT_ALaw_44kHzMono, DISPID_SRCEAdaptation, DISPID_SGRName,
    SPPS_NotOverriden, DISPID_SLPs_NewEnum,
    DISPID_SPIGetDisplayAttributes, SPRST_ACTIVE,
    SpeechRecoProfileProperties, SP_VISEME_3, SVP_7, SP_VISEME_14,
    SGDSActiveWithAutoPause, SVF_Emphasis, SASClosed,
    DISPID_SPERetainedStreamOffset, SASPause, SAFT24kHz8BitStereo,
    STCAll, ISpRecognizer3, DISPID_SCSBaseStream, SPEI_HYPOTHESIS,
    Speech_Max_Pron_Length, SPPHRASEREPLACEMENT, DISPID_SRGRules,
    DISPID_SGRAttributes, DISPID_SRRRecoContext, SGDSActive,
    DISPID_SGRSTText, DISPID_SPEAudioSizeBytes, eLEXTYPE_RESERVED10,
    SRCS_Enabled, ISpeechAudioFormat, DISPID_SRAudioInput,
    DISPID_SRRSpeakAudio, SAFTGSM610_11kHzMono, SPAS_STOP, SPPS_Verb,
    SPEI_END_INPUT_STREAM, SPPS_Noun, ISpeechWaveFormatEx,
    SpObjectToken, SVPNormal, DISPID_SPANumberOfElementsInResult,
    DISPID_SRRGetXMLErrorInfo, SSFMCreate, SGRSTTWildcard,
    DISPID_SPIGrammarId, SREPropertyNumChange, eLEXTYPE_MORPHOLOGY,
    SPEI_START_SR_STREAM, SPAS_PAUSE, DISPID_SLWsCount, SPLO_STATIC,
    DISPID_SPRsCount, SPGS_DISABLED, SPSHT_EMAIL,
    SAFTCCITT_uLaw_44kHzMono, DISPID_SOTId, SPPS_SuppressWord,
    DISPID_SADefaultFormat, ISpeechFileStream, SPEVENT,
    ISpeechRecognizer, DISPID_SRRAudio, WSTRING, SECFNoSpecialChars,
    SpNotifyTranslator, SPAR_High, DISPID_SVEventInterests,
    SpeechAddRemoveWord, SPDKL_CurrentConfig,
    DISPID_SPPNumberOfElements, SAFT8kHz8BitStereo,
    DISPID_SRCAudioInInterferenceStatus, SPAO_RETAIN_AUDIO,
    SPWT_DISPLAY, SPCT_SUB_DICTATION, SPPS_Modifier,
    ISpeechGrammarRule, eLEXTYPE_PRIVATE14,
    ISpPhoneticAlphabetSelection, SP_VISEME_12, DISPID_SLWLangId,
    SPRST_NUM_STATES, DISPID_SRRAlternates, SRARoot,
    DISPID_SASCurrentDevicePosition, DISPID_SGRsItem, ISpPhrase,
    SRAORetainAudio, SPSHT_OTHER, ISpeechGrammarRules, SPEI_SOUND_END,
    SSSPTRelativeToEnd, DISPID_SRRPhraseInfo, DISPID_SRRTStreamTime,
    DISPID_SVSInputSentencePosition, DISPID_SPRuleId,
    SPWP_UNKNOWN_WORD_UNPRONOUNCEABLE, DISPID_SPRuleNumberOfElements,
    DISPID_SRCResume, typelib_path, SPPS_RESERVED3, ISpProperties,
    SAFT22kHz16BitMono, SPSHORTCUTPAIRLIST, SpPhoneConverter,
    SAFTADPCM_8kHzStereo, DISPID_SVEAudioLevel,
    DISPID_SVGetAudioInputs, SpeechCategoryRecognizers,
    SpeechGrammarTagUnlimitedDictation, DISPID_SOTCSetId,
    IInternetSecurityManager, SpeechGrammarTagWildcard,
    __MIDL___MIDL_itf_sapi_0000_0020_0002, DISPID_SRRTimes,
    SPEI_FALSE_RECOGNITION, SPSMF_SRGS_SAPIPROPERTIES,
    DISPID_SPPValue, SREStreamEnd, SAFTADPCM_11kHzMono, SFTInput,
    DISPID_SPIEngineId, SPWORD, DISPID_SPRsItem, SpFileStream,
    SP_VISEME_5, SAFTADPCM_44kHzStereo, _ULARGE_INTEGER,
    SpeechCategoryVoices, DISPID_SOTGetAttribute, tagSTATSTG,
    SPGS_ENABLED, IInternetSecurityMgrSite, SVSFlagsAsync,
    SRERecoOtherContext, SpeechRegistryLocalMachineRoot,
    DISPID_SRGDictationSetState, SVSFParseSsml,
    DISPID_SASCurrentSeekPosition, DISPID_SGRAddResource, SINone,
    DISPID_SLWType, DISPID_SABIBufferSize, SGRSTTDictation,
    DISPID_SPRFirstElement, DISPID_SVAudioOutput,
    DISPID_SAFGetWaveFormatEx, SpAudioFormat, SPCT_COMMAND, SDTRule,
    ISpeechRecoGrammar, SAFT12kHz16BitMono, DISPID_SOTIsUISupported,
    DISPID_SRSetPropertyString, WAVEFORMATEX, SLOStatic,
    ISpeechLexiconPronunciation, DISPID_SRCRetainedAudio,
    SPEI_ADAPTATION, SpeechRegistryUserRoot, SPRS_INACTIVE,
    eLEXTYPE_PRIVATE12, SAFT11kHz16BitStereo, SAFT16kHz8BitMono,
    SVSFIsFilename, DISPID_SMSALineId, SPEI_MIN_TTS,
    SAFTCCITT_ALaw_22kHzStereo, DISPID_SPEActualConfidence,
    DISPID_SASetState, DISPID_SGRsCount, SPWT_PRONUNCIATION,
    SPBO_AHEAD, DISPID_SRCERecognizerStateChange,
    DISPID_SRCESoundStart, ISpeechLexicon,
    SpeechPropertyComplexResponseSpeed, ISpAudio,
    DISPID_SPEPronunciation, DISPID_SRRTLength, DISPID_SPIStartTime,
    SAFT8kHz16BitMono, SpCustomStream, SPEI_PROPERTY_STRING_CHANGE,
    SPCT_SLEEP, DISPID_SVSkip, DISPID_SDKEnumValues,
    ISpPhoneConverter, DISPID_SRGDictationUnload, SVP_0,
    DISPID_SAFGuid, SGSEnabled, SPEI_PHONEME, _ISpeechVoiceEvents,
    DISPID_SGRsFindRule, SpeechAudioFormatGUIDWave, SpResourceManager,
    SPEVENTSOURCEINFO, ULONG_PTR, DISPID_SASFreeBufferSpace,
    _FILETIME, SpStreamFormatConverter, DISPID_SRCEPhraseStart,
    SpMMAudioIn, SAFTCCITT_ALaw_44kHzStereo, SPPS_RESERVED1,
    SPDKL_CurrentUser, DISPID_SVRate, SECNormalConfidence,
    SVSFNLPMask, SPEI_VISEME, DISPID_SLWWord,
    SPINTERFERENCE_LATENCY_WARNING, SAFTCCITT_uLaw_8kHzStereo,
    SLODynamic, ISpeechPhraseProperties, DISPID_SRRGetXMLResult,
    DISPID_SOTCGetDataKey, SPSERIALIZEDPHRASE, DISPID_SRRTTickCount,
    SRESoundStart, ISpNotifyTranslator, COMMETHOD, SPEI_MAX_TTS,
    SPEI_SOUND_START, SP_VISEME_0, SVP_13, DISPID_SRCVoice,
    ISpeechResourceLoader, ISpSerializeState, DISPID_SOTRemove,
    STSF_CommonAppData, DISPID_SBSRead, SVPAlert,
    DISPID_SLGetPronunciations, SWTDeleted, SP_VISEME_8,
    SVESentenceBoundary, eLEXTYPE_PRIVATE20, DISPID_SRRSaveToMemory,
    DISPID_SPIRetainedSizeBytes, eLEXTYPE_RESERVED7, SDKLCurrentUser,
    SBONone, SPINTERFERENCE_NONE, DISPID_SDKSetBinaryValue, SRAONone,
    DISPID_SGRId, eLEXTYPE_VENDORLEXICON, DISPID_SVEVoiceChange,
    IEnumSpObjectTokens, ISpPhoneticAlphabetConverter,
    SGDSActiveUserDelimited, eLEXTYPE_APP, SPWF_SRENGINE,
    SPVPRI_ALERT, SDTAudio, DISPID_SRSNumberOfActiveRules,
    DISPID_SDKEnumKeys, DISPID_SWFEAvgBytesPerSec,
    DISPID_SRCRequestedUIType, SAFTCCITT_uLaw_11kHzStereo, SpStream,
    SPSNoun, DISPID_SRSCurrentStreamNumber, DISPID_SRCCreateGrammar,
    DISPID_SDKDeleteValue, ISpDataKey, SAFT11kHz16BitMono,
    SVEBookmark, SpeechAudioVolume, STSF_FlagCreate,
    SAFTADPCM_8kHzMono, DISPID_SDKDeleteKey,
    ISpeechGrammarRuleStateTransitions, SpeechTokenKeyUI,
    SpeechUserTraining, SECLowConfidence, ISpeechRecoResult2,
    DISPID_SOTCreateInstance, SREStreamStart, SREAudioLevel,
    SVSFUnusedFlags, SPDKL_DefaultLocation, SPSFunction,
    ISpRecoGrammar, SPRS_ACTIVE, ISpeechRecoResultTimes, SITooLoud,
    DISPID_SLAddPronunciation, SRSInactive,
    SDA_Consume_Leading_Spaces, DISPID_SPIAudioSizeBytes,
    DISPID_SPPEngineConfidence, ISpeechPhraseAlternate,
    SPEI_PHRASE_START, DISPID_SLPType, SSFMOpenReadWrite,
    DISPID_SBSWrite, UINT_PTR, SPSERIALIZEDRESULT,
    DISPID_SOTMatchesAttributes, SpeechPropertyResponseSpeed,
    DISPID_SPEs_NewEnum, DISPID_SVIsUISupported, SDTAlternates,
    DISPID_SOTsCount, SPRULE, Library, eLEXTYPE_RESERVED6,
    DISPID_SASState, DISPID_SPAsItem, ISpeechCustomStream,
    DISPID_SGRSAddWordTransition, SAFTGSM610_22kHzMono,
    DISPID_SVVolume, DISPID_SRIsUISupported,
    DISPID_SVSInputSentenceLength, DISPID_SRGSetWordSequenceData,
    SRESoundEnd, DISPID_SLGenerationId, DISPID_SRCEHypothesis,
    SAFT22kHz16BitStereo, DISPID_SFSClose, ISpeechRecognizerStatus,
    SpShortcut, SPRST_INACTIVE_WITH_PURGE,
    SPWP_UNKNOWN_WORD_PRONOUNCEABLE, SRAExport, SRCS_Disabled,
    SPINTERFERENCE_TOOLOUD, DISPID_SRCEventInterests,
    DISPID_SDKOpenKey, DISPID_SRGState, DISPID_SRGIsPronounceable,
    SpeechCategoryAudioIn, SpeechCategoryPhoneConverters, ISpStream,
    eLEXTYPE_PRIVATE16, DISPID_SPPChildren, SPCS_ENABLED, SVP_1,
    DISPID_SBSSeek, SAFTCCITT_uLaw_44kHzStereo,
    DISPID_SGRSAddRuleTransition, SDA_Two_Trailing_Spaces, SAFTText,
    _ISpeechRecoContextEvents, DISPID_SPPs_NewEnum,
    SpeechAudioFormatGUIDText, SPSSuppressWord, SP_VISEME_16,
    DISPID_SVSCurrentStreamNumber, IEnumString, SSFMCreateForWrite,
    SDTDisplayText, DISPID_SDKSetStringValue,
    SpeechPropertyHighConfidenceThreshold, DISPID_SVEStreamStart,
    SPWORDPRONUNCIATION, DISPID_SGRSTransitions,
    DISPID_SPRules_NewEnum, eLEXTYPE_PRIVATE9, SPPHRASEELEMENT,
    SVF_Stressed, DISPID_SPEDisplayText, SpeechPropertyResourceUsage,
    SECFIgnoreWidth, SPSMF_SAPI_PROPERTIES, ISpeechPhraseRules,
    SPGS_EXCLUSIVE, SVP_19, SPEI_RESERVED1, SDKLDefaultLocation,
    SGRSTTWord, SPSNotOverriden, SPSInterjection, SFTSREngine,
    SP_VISEME_6, SREPrivate, ISpStreamFormat, SAFT12kHz8BitStereo,
    SVSFParseSapi, SPRECOCONTEXTSTATUS, ISpMMSysAudio,
    SpPhoneticAlphabetConverter, ISpNotifySink,
    DISPID_SRGetPropertyString, SpTextSelectionInformation,
    DISPID_SPEAudioStreamOffset, wireHWND, DISPID_SRRecognizer,
    DISPID_SGRSTsCount, DISPID_SVSpeakCompleteEvent, SPPS_Function,
    DISPID_SRState, SP_VISEME_7, SPEI_TTS_AUDIO_LEVEL, DISPID_SPPId,
    DISPID_SWFEExtraData, SpInprocRecognizer, SP_VISEME_2, SPSVerb,
    eLEXTYPE_RESERVED4, DISPID_SRGetFormat, DISPID_SVSRunningState,
    SWPUnknownWordUnpronounceable, eLEXTYPE_PRIVATE6,
    SPINTERFERENCE_TOOFAST, __MIDL___MIDL_itf_sapi_0000_0020_0001,
    SVP_11, SSTTTextBuffer, DISPID_SAFType, DISPID_SVWaitUntilDone,
    SLTApp, ISpeechPhraseReplacements, SVSFPurgeBeforeSpeak,
    ISpObjectTokenCategory, DISPID_SOTs_NewEnum, DISPID_SOTCategory,
    DISPID_SDKSetLongValue, SITooQuiet, DISPID_SRSAudioStatus,
    eLEXTYPE_PRIVATE2, DISPID_SOTSetId, SPLO_DYNAMIC,
    DISPID_SPEAudioTimeOffset, eLEXTYPE_PRIVATE3, SP_VISEME_17,
    DISPID_SVSVisemeId, SpInProcRecoContext, SGSExclusive,
    SPPS_Interjection, DISPID_SRRDiscardResultInfo, helpstring,
    DISPID_SLRemovePronunciationByPhoneIds, ISpeechDataKey,
    DISPID_SLRemovePronunciation, SVP_14, DISPID_SMSSetData,
    ISpRecognizer2, SRTSMLTimeout, SAFT24kHz16BitStereo,
    DISPID_SGRs_NewEnum, SVEViseme, SASRun, SRAInterpreter,
    DISPID_SRCSetAdaptationData, SVSFParseAutodetect, SVPOver,
    SAFTCCITT_ALaw_8kHzMono, SPPS_LMA, SINoSignal,
    SpeechDictationTopicSpelling, DISPID_SGRSAddSpecialTransition,
    DISPID_SRCERecognition, SWPKnownWordPronounceable,
    SPWT_LEXICAL_NO_SPECIAL_CHARS, SPTEXTSELECTIONINFO,
    SPINTERFERENCE_NOISE, DISPID_SRGSetTextSelection,
    SPSMF_SRGS_SEMANTICINTERPRETATION_MS, ISpeechXMLRecoResult,
    SGDisplay, DISPID_SPCLangId, DISPID_SPIReplacements,
    DISPID_SFSOpen, DISPID_SPRulesItem, SPEI_START_INPUT_STREAM,
    SAFT32kHz16BitMono, DISPID_SRCERecognitionForOtherContext,
    DISPID_SPISaveToMemory, SVSFDefault, _LARGE_INTEGER, SPPHRASERULE,
    DISPID_SPAStartElementInResult, SVP_12,
    DISPID_SRGCmdLoadFromProprietaryGrammar, SVEWordBoundary,
    SPEI_END_SR_STREAM, DISPID_SPRuleEngineConfidence, SP_VISEME_18,
    SpCompressedLexicon, DISPID_SPERequiredConfidence,
    DISPID_SPPBRestorePhraseFromMemory, SPEI_RECO_OTHER_CONTEXT,
    SpeechCategoryAudioOut, SREAdaptation, ISpNotifySource,
    ISpeechMemoryStream, SP_VISEME_11, ISpObjectToken,
    DISPID_SWFEBlockAlign, SPFM_CREATE, DISPID_SRCEStartStream,
    ISpeechTextSelectionInformation, ISpeechPhraseAlternates,
    SPEI_SR_AUDIO_LEVEL, SPFM_CREATE_ALWAYS, SPEI_UNDEFINED,
    eLEXTYPE_USER_SHORTCUT, SpMemoryStream, DISPID_SRAudioInputStream,
    SPSMF_UPS, DISPID_SRCERequestUI, SAFTCCITT_ALaw_8kHzStereo,
    SVEEndInputStream, SPEI_RESERVED6, SDA_No_Trailing_Space,
    SAFT48kHz16BitStereo, SpObjectTokenCategory, SVSFIsXML,
    SAFT16kHz8BitStereo, DISPID_SVVoice, SpMMAudioOut,
    SPBINARYGRAMMAR, DISPID_SRGCmdSetRuleState, DISPID_SRCBookmark,
    DISPID_SVEPhoneme, SVSFIsNotXML, ISpeechRecoResultDispatch,
    DISPID_SGRAddState, DISPID_SLGetWords, SAFT16kHz16BitMono,
    SAFT44kHz16BitMono, SAFT32kHz8BitStereo, DISPID_SPRText,
    ISpeechPhraseProperty, SVP_18, SPEI_SR_BOOKMARK, SVP_20,
    DISPID_SVSLastBookmarkId, SREStateChange, SVSFVoiceMask,
    SPEI_TTS_BOOKMARK, SRADynamic, SAFTCCITT_ALaw_11kHzStereo,
    SITooFast, DISPID_SGRInitialState, SpeechAudioProperties,
    ISpeechLexiconWords, DISPID_SPPsCount, ISpeechGrammarRuleState,
    SPFM_OPEN_READONLY, DISPID_SPEEngineConfidence,
    SAFT11kHz8BitStereo, DISPID_SGRSRule, _lcid, SVF_None,
    eLEXTYPE_PRIVATE18, SPPS_Unknown, DISPID_SVSpeak, SPSHT_Unknown,
    SAFTTrueSpeech_8kHz1BitMono, SVEVoiceChange,
    SPINTERFERENCE_LATENCY_TRUNCATE_BEGIN, SREInterference,
    DISPID_SBSFormat, ISpPhraseAlt, DISPID_SRGCommit,
    DISPID_SGRSTWeight, ISpeechObjectTokenCategory, SP_VISEME_9,
    SPFM_NUM_MODES, SpeechPropertyAdaptationOn, __MIDL_IWinTypes_0009,
    ISpeechPhraseInfoBuilder, SPEI_RESERVED2, SPSHT_NotOverriden,
    SPCT_DICTATION, DISPID_SVGetVoices, DISPID_SPPFirstElement,
    _RemotableHandle, ISpeechGrammarRuleStateTransition,
    DISPID_SGRsCommitAndSave, DISPID_SRGCmdLoadFromMemory,
    SAFT16kHz16BitStereo, DISPID_SGRClear, SDKLCurrentConfig,
    SpeechTokenKeyAttributes, DISPID_SPRuleName, DISPID_SOTDataKey,
    SDA_One_Trailing_Space,
    DISPID_SRAllowAudioInputFormatChangesOnNextSet, ISpRecoContext,
    DISPID_SOTDisplayUI, SAFTCCITT_uLaw_22kHzStereo, DISPID_SGRSTType,
    SAFTADPCM_44kHzMono, DISPID_SLPPartOfSpeech, SWTAdded,
    STCInprocHandler, DISPID_SVSLastResult, SRSActive,
    SGPronounciation, eLEXTYPE_PRIVATE10, SASStop,
    SpUnCompressedLexicon, DISPID_SMSGetData, SPPS_RESERVED4,
    SPRECOGNIZERSTATUS, SpeechGrammarTagDictation,
    DISPID_SASNonBlockingIO, Speech_StreamPos_Asap, SREBookmark,
    DISPID_SPAs_NewEnum, SPEI_INTERFERENCE, DISPID_SRIsShared,
    SpLexicon, SSSPTRelativeToStart, SAFT44kHz8BitStereo,
    SP_VISEME_20, DISPID_SVEEnginePrivate, DISPID_SAStatus,
    DISPID_SPRuleParent, SVP_15, DISPID_SVAudioOutputStream,
    SPINTERFERENCE_LATENCY_TRUNCATE_END, SRTAutopause,
    DISPID_SRGDictationLoad, SP_VISEME_10, DISPID_SVEViseme,
    DISPID_SPEsItem, SVP_2, SAFTADPCM_22kHzStereo, SDTPronunciation,
    DISPID_SPELexicalForm, DISPID_SRCreateRecoContext, SPRST_INACTIVE,
    DISPID_SREmulateRecognition, DISPID_SRRSetTextFeedback,
    SPINTERFERENCE_TOOQUIET, eLEXTYPE_PRIVATE15,
    SPRS_ACTIVE_USER_DELIMITED, SAFTCCITT_ALaw_22kHzMono,
    SRERequestUI, SPPROPERTYINFO, DISPID_SRGCmdLoadFromResource,
    ISpRecoResult, ISpeechPhraseElements, SpSharedRecognizer,
    SP_VISEME_19, DISPID_SPAPhraseInfo, ISpeechRecoResult,
    Speech_StreamPos_RealTime, DISPID_SGRsAdd,
    DISPID_SVAllowAudioOuputFormatChangesOnNextSet,
    SAFTADPCM_22kHzMono, SpeechPropertyLowConfidenceThreshold,
    eLEXTYPE_LETTERTOSOUND, DISPID_SPERetainedSizeBytes,
    SAFT22kHz8BitMono, SSTTDictation, SSSPTRelativeToCurrentPosition,
    tagSPTEXTSELECTIONINFO, SVP_10, DISPID_SGRsDynamic, VARIANT,
    DISPID_SOTRemoveStorageFileName, SVP_17, DISPID_SRStatus,
    DISPID_SPRuleFirstElement, SAFT48kHz16BitMono, SP_VISEME_13,
    SAFT8kHz16BitStereo, STCLocalServer, SPINTERFERENCE_TOOSLOW,
    IStream, DISPID_SOTsItem, ISpeechPhoneConverter,
    tagSPPROPERTYINFO, BSTR, SGDSInactive, DISPID_SVSpeakStream,
    SpWaveFormatEx, SPSLMA, DISPIDSPTSI_ActiveOffset,
    ISpeechRecoContext, SPPHRASEPROPERTY, SpNullPhoneConverter,
    SAFT32kHz8BitMono, ISpeechBaseStream, DISPID_SLWsItem,
    DISPID_SVSInputWordPosition, Speech_Default_Weight,
    DISPID_SRCCreateResultFromMemory, SpMMAudioEnum,
    SAFTCCITT_uLaw_8kHzMono, SVEPhoneme, SPRS_ACTIVE_WITH_AUTO_PAUSE,
    DISPID_SRCEAudioLevel, SDTProperty, ISpXMLRecoResult,
    ISequentialStream, IServiceProvider, SPEI_RESERVED5,
    DISPID_SLPPhoneIds, DISPID_SRGReset, SGRSTTEpsilon,
    DISPID_SPILanguageId, SPAO_NONE, DISPID_SRCEEndStream, SGRSTTRule,
    DISPID_SABufferNotifySize, SVP_8, DISPID_SPCPhoneToId,
    eLEXTYPE_USER, DISPID_SPARecoResult, SAFT48kHz8BitMono,
    SpeechTokenValueCLSID, SPEI_TTS_PRIVATE, DISPID_SRSClsidEngine,
    DISPID_SPIProperties, SpeechVoiceSkipTypeSentence,
    SVEStartInputStream, SPAR_Medium, SAFT32kHz16BitStereo,
    SPEI_MIN_SR, eLEXTYPE_PRIVATE19, DISPID_SVDisplayUI, SPXRO_SML,
    SpeechTokenIdUserLexicon, DISPID_SWFEFormatTag,
    SAFTGSM610_8kHzMono, ISpeechPhraseRule, SINoise,
    DISPID_SPPConfidence, DISPID_SRGCmdLoadFromFile,
    DISPID_SRAllowVoiceFormatMatchingOnNextSet, DISPID_SVStatus,
    DISPID_SVSPhonemeId, SREPropertyStringChange, eLEXTYPE_PRIVATE11,
    DISPID_SVGetAudioOutputs, SPCS_DISABLED, DISPID_SVGetProfiles,
    SECFIgnoreCase, ISpeechObjectToken, DISPID_SPIEnginePrivateData,
    SPWP_KNOWN_WORD_PRONOUNCEABLE, SpeechAllElements, SGSDisabled,
    SPVPRI_NORMAL, DISPID_SDKCreateKey, SAFT8kHz8BitMono, LONG_PTR,
    SRTReSent, SVEPrivate, DISPID_SRCRetainedAudioFormat, SRTStandard,
    DISPID_SGRSTs_NewEnum, SITooSlow, SPEI_WORD_BOUNDARY,
    SP_VISEME_21, DISPID_SGRSTPropertyName, STSF_AppData,
    SPEI_REQUEST_UI, SPSEMANTICERRORINFO, DISPID_SVESentenceBoundary,
    DISPID_SVSLastBookmark, SAFTExtendedAudioFormat,
    SPINTERFERENCE_NOSIGNAL, DISPID_SAEventHandle, SPEI_RESERVED3,
    CoClass, SAFTADPCM_11kHzStereo, SRSActiveAlways,
    DISPID_SMSAMMHandle, SVSFParseMask, SDTLexicalForm, ISpVoice,
    SVP_5, DISPID_SDKGetStringValue, DISPMETHOD,
    DISPID_SRRAudioFormat, DISPID_SRCEPropertyNumberChange, SPPHRASE,
    eLEXTYPE_RESERVED9, SPBO_NONE, DISPID_SOTCId, _check_version,
    SPAS_CLOSED, DISPID_SRCEEnginePrivate, DISPID_SLWPronunciations,
    DISPID_SPIElements, SPFM_OPEN_READWRITE, SAFT12kHz16BitStereo,
    SAFT24kHz8BitMono, DISPID_SVPriority, DISPID_SVAlertBoundary,
    DISPID_SRCVoicePurgeEvent, ISpObjectWithToken, SBOPause,
    SPEI_PROPERTY_NUM_CHANGE, DISPID_SRCESoundEnd, SPPS_RESERVED2,
    DISPID_SRProfile, SSFMOpenForRead, STCRemoteServer,
    DISPID_SVSyncronousSpeakTimeout, SPWT_LEXICAL, SREAllEvents,
    DISPID_SPACommit, eLEXTYPE_PRIVATE5, DISPID_SPIAudioSizeTime,
    SPAR_Unknown, SAFTCCITT_ALaw_11kHzMono, STSF_LocalAppData,
    SPEI_ACTIVE_CATEGORY_CHANGED, SpeechEngineProperties,
    SGRSTTTextBuffer, DISPID_SDKGetlongValue, SPEI_MAX_SR,
    DISPID_SPAsCount, SPRST_ACTIVE_ALWAYS, SPEI_SR_RETAINEDAUDIO,
    DISPID_SMSADeviceId, eWORDTYPE_ADDED, SPBO_TIME_UNITS,
    SRADefaultToActive, SPEI_SR_PRIVATE, ISpLexicon,
    ISpeechObjectTokens, SLTUser, SPEI_SENTENCE_BOUNDARY,
    DISPID_SRSCurrentStreamPosition, DISPID_SOTGetStorageFileName,
    SAFT22kHz8BitStereo, DISPID_SVSLastStreamNumberQueued,
    ISpEventSink, SPWORDPRONUNCIATIONLIST, DISPID_SPRulesCount,
    ISpShortcut, STCInprocServer, eLEXTYPE_PRIVATE17, SVP_4,
    SpSharedRecoContext, ISpeechPhraseElement, DISPID_SRDisplayUI,
    DISPID_SABufferInfo, ISpeechVoice, DISPID_SRCEBookmark,
    SRTEmulated, eWORDTYPE_DELETED, SRSEDone, SPBO_PAUSE, SP_VISEME_1,
    SpPhraseInfoBuilder, DISPID_SVResume, SP_VISEME_15,
    DISPID_SABIMinNotification, DISPIDSPTSI_ActiveLength,
    eLEXTYPE_PRIVATE1, ISpeechAudio, SVP_16, DISPID_SWFESamplesPerSec
)


class SpeechInterference(IntFlag):
    SINone = 0
    SINoise = 1
    SINoSignal = 2
    SITooLoud = 3
    SITooQuiet = 4
    SITooFast = 5
    SITooSlow = 6


class SpeechRecoEvents(IntFlag):
    SREStreamEnd = 1
    SRESoundStart = 2
    SRESoundEnd = 4
    SREPhraseStart = 8
    SRERecognition = 16
    SREHypothesis = 32
    SREBookmark = 64
    SREPropertyNumChange = 128
    SREPropertyStringChange = 256
    SREFalseRecognition = 512
    SREInterference = 1024
    SRERequestUI = 2048
    SREStateChange = 4096
    SREAdaptation = 8192
    SREStreamStart = 16384
    SRERecoOtherContext = 32768
    SREAudioLevel = 65536
    SREPrivate = 262144
    SREAllEvents = 393215


class SpeechRecoContextState(IntFlag):
    SRCS_Disabled = 0
    SRCS_Enabled = 1


class SpeechRetainedAudioOptions(IntFlag):
    SRAONone = 0
    SRAORetainAudio = 1


class SpeechBookmarkOptions(IntFlag):
    SBONone = 0
    SBOPause = 1


class SPWORDTYPE(IntFlag):
    eWORDTYPE_ADDED = 1
    eWORDTYPE_DELETED = 2


class DISPID_SpeechVoice(IntFlag):
    DISPID_SVStatus = 1
    DISPID_SVVoice = 2
    DISPID_SVAudioOutput = 3
    DISPID_SVAudioOutputStream = 4
    DISPID_SVRate = 5
    DISPID_SVVolume = 6
    DISPID_SVAllowAudioOuputFormatChangesOnNextSet = 7
    DISPID_SVEventInterests = 8
    DISPID_SVPriority = 9
    DISPID_SVAlertBoundary = 10
    DISPID_SVSyncronousSpeakTimeout = 11
    DISPID_SVSpeak = 12
    DISPID_SVSpeakStream = 13
    DISPID_SVPause = 14
    DISPID_SVResume = 15
    DISPID_SVSkip = 16
    DISPID_SVGetVoices = 17
    DISPID_SVGetAudioOutputs = 18
    DISPID_SVWaitUntilDone = 19
    DISPID_SVSpeakCompleteEvent = 20
    DISPID_SVIsUISupported = 21
    DISPID_SVDisplayUI = 22


class SPAUDIOOPTIONS(IntFlag):
    SPAO_NONE = 0
    SPAO_RETAIN_AUDIO = 1


class SPBOOKMARKOPTIONS(IntFlag):
    SPBO_NONE = 0
    SPBO_PAUSE = 1
    SPBO_AHEAD = 2
    SPBO_TIME_UNITS = 4


class SPCONTEXTSTATE(IntFlag):
    SPCS_DISABLED = 0
    SPCS_ENABLED = 1


class SpeechDisplayAttributes(IntFlag):
    SDA_No_Trailing_Space = 0
    SDA_One_Trailing_Space = 2
    SDA_Two_Trailing_Spaces = 4
    SDA_Consume_Leading_Spaces = 8


class SpeechEngineConfidence(IntFlag):
    SECLowConfidence = -1
    SECNormalConfidence = 0
    SECHighConfidence = 1


class SpeechSpecialTransitionType(IntFlag):
    SSTTWildcard = 1
    SSTTDictation = 2
    SSTTTextBuffer = 3


class SPRECOSTATE(IntFlag):
    SPRST_INACTIVE = 0
    SPRST_ACTIVE = 1
    SPRST_ACTIVE_ALWAYS = 2
    SPRST_INACTIVE_WITH_PURGE = 3
    SPRST_NUM_STATES = 4


class SPWAVEFORMATTYPE(IntFlag):
    SPWF_INPUT = 0
    SPWF_SRENGINE = 1


class SpeechLoadOption(IntFlag):
    SLOStatic = 0
    SLODynamic = 1


class SPSHORTCUTTYPE(IntFlag):
    SPSHT_NotOverriden = -1
    SPSHT_Unknown = 0
    SPSHT_EMAIL = 4096
    SPSHT_OTHER = 8192
    SPPS_RESERVED1 = 12288
    SPPS_RESERVED2 = 16384
    SPPS_RESERVED3 = 20480
    SPPS_RESERVED4 = 61440


class SPFILEMODE(IntFlag):
    SPFM_OPEN_READONLY = 0
    SPFM_OPEN_READWRITE = 1
    SPFM_CREATE = 2
    SPFM_CREATE_ALWAYS = 3
    SPFM_NUM_MODES = 4


class SpeechRuleState(IntFlag):
    SGDSInactive = 0
    SGDSActive = 1
    SGDSActiveWithAutoPause = 3
    SGDSActiveUserDelimited = 4


class DISPID_SpeechVoiceStatus(IntFlag):
    DISPID_SVSCurrentStreamNumber = 1
    DISPID_SVSLastStreamNumberQueued = 2
    DISPID_SVSLastResult = 3
    DISPID_SVSRunningState = 4
    DISPID_SVSInputWordPosition = 5
    DISPID_SVSInputWordLength = 6
    DISPID_SVSInputSentencePosition = 7
    DISPID_SVSInputSentenceLength = 8
    DISPID_SVSLastBookmark = 9
    DISPID_SVSLastBookmarkId = 10
    DISPID_SVSPhonemeId = 11
    DISPID_SVSVisemeId = 12


class SpeechVoiceSpeakFlags(IntFlag):
    SVSFDefault = 0
    SVSFlagsAsync = 1
    SVSFPurgeBeforeSpeak = 2
    SVSFIsFilename = 4
    SVSFIsXML = 8
    SVSFIsNotXML = 16
    SVSFPersistXML = 32
    SVSFNLPSpeakPunc = 64
    SVSFParseSapi = 128
    SVSFParseSsml = 256
    SVSFParseAutodetect = 0
    SVSFNLPMask = 64
    SVSFParseMask = 384
    SVSFVoiceMask = 511
    SVSFUnusedFlags = -512


class SpeechDiscardType(IntFlag):
    SDTProperty = 1
    SDTReplacement = 2
    SDTRule = 4
    SDTDisplayText = 8
    SDTLexicalForm = 16
    SDTPronunciation = 32
    SDTAudio = 64
    SDTAlternates = 128
    SDTAll = 255


class SPVPRIORITY(IntFlag):
    SPVPRI_NORMAL = 0
    SPVPRI_ALERT = 1
    SPVPRI_OVER = 2


class SPEVENTENUM(IntFlag):
    SPEI_UNDEFINED = 0
    SPEI_START_INPUT_STREAM = 1
    SPEI_END_INPUT_STREAM = 2
    SPEI_VOICE_CHANGE = 3
    SPEI_TTS_BOOKMARK = 4
    SPEI_WORD_BOUNDARY = 5
    SPEI_PHONEME = 6
    SPEI_SENTENCE_BOUNDARY = 7
    SPEI_VISEME = 8
    SPEI_TTS_AUDIO_LEVEL = 9
    SPEI_TTS_PRIVATE = 15
    SPEI_MIN_TTS = 1
    SPEI_MAX_TTS = 15
    SPEI_END_SR_STREAM = 34
    SPEI_SOUND_START = 35
    SPEI_SOUND_END = 36
    SPEI_PHRASE_START = 37
    SPEI_RECOGNITION = 38
    SPEI_HYPOTHESIS = 39
    SPEI_SR_BOOKMARK = 40
    SPEI_PROPERTY_NUM_CHANGE = 41
    SPEI_PROPERTY_STRING_CHANGE = 42
    SPEI_FALSE_RECOGNITION = 43
    SPEI_INTERFERENCE = 44
    SPEI_REQUEST_UI = 45
    SPEI_RECO_STATE_CHANGE = 46
    SPEI_ADAPTATION = 47
    SPEI_START_SR_STREAM = 48
    SPEI_RECO_OTHER_CONTEXT = 49
    SPEI_SR_AUDIO_LEVEL = 50
    SPEI_SR_RETAINEDAUDIO = 51
    SPEI_SR_PRIVATE = 52
    SPEI_ACTIVE_CATEGORY_CHANGED = 53
    SPEI_RESERVED5 = 54
    SPEI_RESERVED6 = 55
    SPEI_MIN_SR = 34
    SPEI_MAX_SR = 55
    SPEI_RESERVED1 = 30
    SPEI_RESERVED2 = 33
    SPEI_RESERVED3 = 63


class DISPID_SpeechVoiceEvent(IntFlag):
    DISPID_SVEStreamStart = 1
    DISPID_SVEStreamEnd = 2
    DISPID_SVEVoiceChange = 3
    DISPID_SVEBookmark = 4
    DISPID_SVEWord = 5
    DISPID_SVEPhoneme = 6
    DISPID_SVESentenceBoundary = 7
    DISPID_SVEViseme = 8
    DISPID_SVEAudioLevel = 9
    DISPID_SVEEnginePrivate = 10


class _SPAUDIOSTATE(IntFlag):
    SPAS_CLOSED = 0
    SPAS_STOP = 1
    SPAS_PAUSE = 2
    SPAS_RUN = 3


class SpeechWordPronounceable(IntFlag):
    SWPUnknownWordUnpronounceable = 0
    SWPUnknownWordPronounceable = 1
    SWPKnownWordPronounceable = 2


class DISPID_SpeechRecognizer(IntFlag):
    DISPID_SRRecognizer = 1
    DISPID_SRAllowAudioInputFormatChangesOnNextSet = 2
    DISPID_SRAudioInput = 3
    DISPID_SRAudioInputStream = 4
    DISPID_SRIsShared = 5
    DISPID_SRState = 6
    DISPID_SRStatus = 7
    DISPID_SRProfile = 8
    DISPID_SREmulateRecognition = 9
    DISPID_SRCreateRecoContext = 10
    DISPID_SRGetFormat = 11
    DISPID_SRSetPropertyNumber = 12
    DISPID_SRGetPropertyNumber = 13
    DISPID_SRSetPropertyString = 14
    DISPID_SRGetPropertyString = 15
    DISPID_SRIsUISupported = 16
    DISPID_SRDisplayUI = 17
    DISPID_SRGetRecognizers = 18
    DISPID_SVGetAudioInputs = 19
    DISPID_SVGetProfiles = 20


class SpeechTokenContext(IntFlag):
    STCInprocServer = 1
    STCInprocHandler = 2
    STCLocalServer = 4
    STCRemoteServer = 16
    STCAll = 23


class SpeechTokenShellFolder(IntFlag):
    STSF_AppData = 26
    STSF_LocalAppData = 28
    STSF_CommonAppData = 35
    STSF_FlagCreate = 32768


class SpeechFormatType(IntFlag):
    SFTInput = 0
    SFTSREngine = 1


class SPVISEMES(IntFlag):
    SP_VISEME_0 = 0
    SP_VISEME_1 = 1
    SP_VISEME_2 = 2
    SP_VISEME_3 = 3
    SP_VISEME_4 = 4
    SP_VISEME_5 = 5
    SP_VISEME_6 = 6
    SP_VISEME_7 = 7
    SP_VISEME_8 = 8
    SP_VISEME_9 = 9
    SP_VISEME_10 = 10
    SP_VISEME_11 = 11
    SP_VISEME_12 = 12
    SP_VISEME_13 = 13
    SP_VISEME_14 = 14
    SP_VISEME_15 = 15
    SP_VISEME_16 = 16
    SP_VISEME_17 = 17
    SP_VISEME_18 = 18
    SP_VISEME_19 = 19
    SP_VISEME_20 = 20
    SP_VISEME_21 = 21


class SpeechGrammarState(IntFlag):
    SGSEnabled = 1
    SGSDisabled = 0
    SGSExclusive = 3


class SpeechEmulationCompareFlags(IntFlag):
    SECFIgnoreCase = 1
    SECFIgnoreKanaType = 65536
    SECFIgnoreWidth = 131072
    SECFNoSpecialChars = 536870912
    SECFEmulateResult = 1073741824
    SECFDefault = 196609


class SPGRAMMARWORDTYPE(IntFlag):
    SPWT_DISPLAY = 0
    SPWT_LEXICAL = 1
    SPWT_PRONUNCIATION = 2
    SPWT_LEXICAL_NO_SPECIAL_CHARS = 3


class SPLOADOPTIONS(IntFlag):
    SPLO_STATIC = 0
    SPLO_DYNAMIC = 1


class SPRULESTATE(IntFlag):
    SPRS_INACTIVE = 0
    SPRS_ACTIVE = 1
    SPRS_ACTIVE_WITH_AUTO_PAUSE = 3
    SPRS_ACTIVE_USER_DELIMITED = 4


class SPWORDPRONOUNCEABLE(IntFlag):
    SPWP_UNKNOWN_WORD_UNPRONOUNCEABLE = 0
    SPWP_UNKNOWN_WORD_PRONOUNCEABLE = 1
    SPWP_KNOWN_WORD_PRONOUNCEABLE = 2


class SPGRAMMARSTATE(IntFlag):
    SPGS_DISABLED = 0
    SPGS_ENABLED = 1
    SPGS_EXCLUSIVE = 3


class SpeechDataKeyLocation(IntFlag):
    SDKLDefaultLocation = 0
    SDKLCurrentUser = 1
    SDKLLocalMachine = 2
    SDKLCurrentConfig = 5


class DISPID_SpeechRecognizerStatus(IntFlag):
    DISPID_SRSAudioStatus = 1
    DISPID_SRSCurrentStreamPosition = 2
    DISPID_SRSCurrentStreamNumber = 3
    DISPID_SRSNumberOfActiveRules = 4
    DISPID_SRSClsidEngine = 5
    DISPID_SRSSupportedLanguages = 6


class SPSEMANTICFORMAT(IntFlag):
    SPSMF_SAPI_PROPERTIES = 0
    SPSMF_SRGS_SEMANTICINTERPRETATION_MS = 1
    SPSMF_SRGS_SAPIPROPERTIES = 2
    SPSMF_UPS = 4
    SPSMF_SRGS_SEMANTICINTERPRETATION_W3C = 8


class DISPID_SpeechRecoContext(IntFlag):
    DISPID_SRCRecognizer = 1
    DISPID_SRCAudioInInterferenceStatus = 2
    DISPID_SRCRequestedUIType = 3
    DISPID_SRCVoice = 4
    DISPID_SRAllowVoiceFormatMatchingOnNextSet = 5
    DISPID_SRCVoicePurgeEvent = 6
    DISPID_SRCEventInterests = 7
    DISPID_SRCCmdMaxAlternates = 8
    DISPID_SRCState = 9
    DISPID_SRCRetainedAudio = 10
    DISPID_SRCRetainedAudioFormat = 11
    DISPID_SRCPause = 12
    DISPID_SRCResume = 13
    DISPID_SRCCreateGrammar = 14
    DISPID_SRCCreateResultFromMemory = 15
    DISPID_SRCBookmark = 16
    DISPID_SRCSetAdaptationData = 17


class SpeechRuleAttributes(IntFlag):
    SRATopLevel = 1
    SRADefaultToActive = 2
    SRAExport = 4
    SRAImport = 8
    SRAInterpreter = 16
    SRADynamic = 32
    SRARoot = 64


class DISPIDSPRG(IntFlag):
    DISPID_SRGId = 1
    DISPID_SRGRecoContext = 2
    DISPID_SRGState = 3
    DISPID_SRGRules = 4
    DISPID_SRGReset = 5
    DISPID_SRGCommit = 6
    DISPID_SRGCmdLoadFromFile = 7
    DISPID_SRGCmdLoadFromObject = 8
    DISPID_SRGCmdLoadFromResource = 9
    DISPID_SRGCmdLoadFromMemory = 10
    DISPID_SRGCmdLoadFromProprietaryGrammar = 11
    DISPID_SRGCmdSetRuleState = 12
    DISPID_SRGCmdSetRuleIdState = 13
    DISPID_SRGDictationLoad = 14
    DISPID_SRGDictationUnload = 15
    DISPID_SRGDictationSetState = 16
    DISPID_SRGSetWordSequenceData = 17
    DISPID_SRGSetTextSelection = 18
    DISPID_SRGIsPronounceable = 19


class SPXMLRESULTOPTIONS(IntFlag):
    SPXRO_SML = 0
    SPXRO_Alternates_SML = 1


class SpeechGrammarWordType(IntFlag):
    SGDisplay = 0
    SGLexical = 1
    SGPronounciation = 2
    SGLexicalNoSpecialChars = 3


class DISPID_SpeechRecoContextEvents(IntFlag):
    DISPID_SRCEStartStream = 1
    DISPID_SRCEEndStream = 2
    DISPID_SRCEBookmark = 3
    DISPID_SRCESoundStart = 4
    DISPID_SRCESoundEnd = 5
    DISPID_SRCEPhraseStart = 6
    DISPID_SRCERecognition = 7
    DISPID_SRCEHypothesis = 8
    DISPID_SRCEPropertyNumberChange = 9
    DISPID_SRCEPropertyStringChange = 10
    DISPID_SRCEFalseRecognition = 11
    DISPID_SRCEInterference = 12
    DISPID_SRCERequestUI = 13
    DISPID_SRCERecognizerStateChange = 14
    DISPID_SRCEAdaptation = 15
    DISPID_SRCERecognitionForOtherContext = 16
    DISPID_SRCEAudioLevel = 17
    DISPID_SRCEEnginePrivate = 18


class SpeechVisemeFeature(IntFlag):
    SVF_None = 0
    SVF_Stressed = 1
    SVF_Emphasis = 2


class SpeechVisemeType(IntFlag):
    SVP_0 = 0
    SVP_1 = 1
    SVP_2 = 2
    SVP_3 = 3
    SVP_4 = 4
    SVP_5 = 5
    SVP_6 = 6
    SVP_7 = 7
    SVP_8 = 8
    SVP_9 = 9
    SVP_10 = 10
    SVP_11 = 11
    SVP_12 = 12
    SVP_13 = 13
    SVP_14 = 14
    SVP_15 = 15
    SVP_16 = 16
    SVP_17 = 17
    SVP_18 = 18
    SVP_19 = 19
    SVP_20 = 20
    SVP_21 = 21


class SpeechRecognitionType(IntFlag):
    SRTStandard = 0
    SRTAutopause = 1
    SRTEmulated = 2
    SRTSMLTimeout = 4
    SRTExtendableParse = 8
    SRTReSent = 16


class SpeechAudioState(IntFlag):
    SASClosed = 0
    SASStop = 1
    SASPause = 2
    SASRun = 3


class SpeechAudioFormatType(IntFlag):
    SAFTDefault = -1
    SAFTNoAssignedFormat = 0
    SAFTText = 1
    SAFTNonStandardFormat = 2
    SAFTExtendedAudioFormat = 3
    SAFT8kHz8BitMono = 4
    SAFT8kHz8BitStereo = 5
    SAFT8kHz16BitMono = 6
    SAFT8kHz16BitStereo = 7
    SAFT11kHz8BitMono = 8
    SAFT11kHz8BitStereo = 9
    SAFT11kHz16BitMono = 10
    SAFT11kHz16BitStereo = 11
    SAFT12kHz8BitMono = 12
    SAFT12kHz8BitStereo = 13
    SAFT12kHz16BitMono = 14
    SAFT12kHz16BitStereo = 15
    SAFT16kHz8BitMono = 16
    SAFT16kHz8BitStereo = 17
    SAFT16kHz16BitMono = 18
    SAFT16kHz16BitStereo = 19
    SAFT22kHz8BitMono = 20
    SAFT22kHz8BitStereo = 21
    SAFT22kHz16BitMono = 22
    SAFT22kHz16BitStereo = 23
    SAFT24kHz8BitMono = 24
    SAFT24kHz8BitStereo = 25
    SAFT24kHz16BitMono = 26
    SAFT24kHz16BitStereo = 27
    SAFT32kHz8BitMono = 28
    SAFT32kHz8BitStereo = 29
    SAFT32kHz16BitMono = 30
    SAFT32kHz16BitStereo = 31
    SAFT44kHz8BitMono = 32
    SAFT44kHz8BitStereo = 33
    SAFT44kHz16BitMono = 34
    SAFT44kHz16BitStereo = 35
    SAFT48kHz8BitMono = 36
    SAFT48kHz8BitStereo = 37
    SAFT48kHz16BitMono = 38
    SAFT48kHz16BitStereo = 39
    SAFTTrueSpeech_8kHz1BitMono = 40
    SAFTCCITT_ALaw_8kHzMono = 41
    SAFTCCITT_ALaw_8kHzStereo = 42
    SAFTCCITT_ALaw_11kHzMono = 43
    SAFTCCITT_ALaw_11kHzStereo = 44
    SAFTCCITT_ALaw_22kHzMono = 45
    SAFTCCITT_ALaw_22kHzStereo = 46
    SAFTCCITT_ALaw_44kHzMono = 47
    SAFTCCITT_ALaw_44kHzStereo = 48
    SAFTCCITT_uLaw_8kHzMono = 49
    SAFTCCITT_uLaw_8kHzStereo = 50
    SAFTCCITT_uLaw_11kHzMono = 51
    SAFTCCITT_uLaw_11kHzStereo = 52
    SAFTCCITT_uLaw_22kHzMono = 53
    SAFTCCITT_uLaw_22kHzStereo = 54
    SAFTCCITT_uLaw_44kHzMono = 55
    SAFTCCITT_uLaw_44kHzStereo = 56
    SAFTADPCM_8kHzMono = 57
    SAFTADPCM_8kHzStereo = 58
    SAFTADPCM_11kHzMono = 59
    SAFTADPCM_11kHzStereo = 60
    SAFTADPCM_22kHzMono = 61
    SAFTADPCM_22kHzStereo = 62
    SAFTADPCM_44kHzMono = 63
    SAFTADPCM_44kHzStereo = 64
    SAFTGSM610_8kHzMono = 65
    SAFTGSM610_11kHzMono = 66
    SAFTGSM610_22kHzMono = 67
    SAFTGSM610_44kHzMono = 68


class SpeechGrammarRuleStateTransitionType(IntFlag):
    SGRSTTEpsilon = 0
    SGRSTTWord = 1
    SGRSTTRule = 2
    SGRSTTDictation = 3
    SGRSTTWildcard = 4
    SGRSTTTextBuffer = 5


class SpeechLexiconType(IntFlag):
    SLTUser = 1
    SLTApp = 2


class SpeechPartOfSpeech(IntFlag):
    SPSNotOverriden = -1
    SPSUnknown = 0
    SPSNoun = 4096
    SPSVerb = 8192
    SPSModifier = 12288
    SPSFunction = 16384
    SPSInterjection = 20480
    SPSLMA = 28672
    SPSSuppressWord = 61440


class DISPID_SpeechGrammarRule(IntFlag):
    DISPID_SGRAttributes = 1
    DISPID_SGRInitialState = 2
    DISPID_SGRName = 3
    DISPID_SGRId = 4
    DISPID_SGRClear = 5
    DISPID_SGRAddResource = 6
    DISPID_SGRAddState = 7


class DISPID_SpeechGrammarRules(IntFlag):
    DISPID_SGRsCount = 1
    DISPID_SGRsDynamic = 2
    DISPID_SGRsAdd = 3
    DISPID_SGRsCommit = 4
    DISPID_SGRsCommitAndSave = 5
    DISPID_SGRsFindRule = 6
    DISPID_SGRsItem = 0
    DISPID_SGRs_NewEnum = -4


class SpeechStreamSeekPositionType(IntFlag):
    SSSPTRelativeToStart = 0
    SSSPTRelativeToCurrentPosition = 1
    SSSPTRelativeToEnd = 2


class DISPID_SpeechGrammarRuleState(IntFlag):
    DISPID_SGRSRule = 1
    DISPID_SGRSTransitions = 2
    DISPID_SGRSAddWordTransition = 3
    DISPID_SGRSAddRuleTransition = 4
    DISPID_SGRSAddSpecialTransition = 5


class DISPID_SpeechGrammarRuleStateTransition(IntFlag):
    DISPID_SGRSTType = 1
    DISPID_SGRSTText = 2
    DISPID_SGRSTRule = 3
    DISPID_SGRSTWeight = 4
    DISPID_SGRSTPropertyName = 5
    DISPID_SGRSTPropertyId = 6
    DISPID_SGRSTPropertyValue = 7
    DISPID_SGRSTNextState = 8


class SpeechWordType(IntFlag):
    SWTAdded = 1
    SWTDeleted = 2


class DISPID_SpeechGrammarRuleStateTransitions(IntFlag):
    DISPID_SGRSTsCount = 1
    DISPID_SGRSTsItem = 0
    DISPID_SGRSTs_NewEnum = -4


class DISPID_SpeechLexiconWords(IntFlag):
    DISPID_SLWsCount = 1
    DISPID_SLWsItem = 0
    DISPID_SLWs_NewEnum = -4


class DISPIDSPTSI(IntFlag):
    DISPIDSPTSI_ActiveOffset = 1
    DISPIDSPTSI_ActiveLength = 2
    DISPIDSPTSI_SelectionOffset = 3
    DISPIDSPTSI_SelectionLength = 4


class DISPID_SpeechLexiconWord(IntFlag):
    DISPID_SLWLangId = 1
    DISPID_SLWType = 2
    DISPID_SLWWord = 3
    DISPID_SLWPronunciations = 4


class DISPID_SpeechRecoResult(IntFlag):
    DISPID_SRRRecoContext = 1
    DISPID_SRRTimes = 2
    DISPID_SRRAudioFormat = 3
    DISPID_SRRPhraseInfo = 4
    DISPID_SRRAlternates = 5
    DISPID_SRRAudio = 6
    DISPID_SRRSpeakAudio = 7
    DISPID_SRRSaveToMemory = 8
    DISPID_SRRDiscardResultInfo = 9


class DISPID_SpeechLexiconProns(IntFlag):
    DISPID_SLPsCount = 1
    DISPID_SLPsItem = 0
    DISPID_SLPs_NewEnum = -4


class DISPID_SpeechLexiconPronunciation(IntFlag):
    DISPID_SLPType = 1
    DISPID_SLPLangId = 2
    DISPID_SLPPartOfSpeech = 3
    DISPID_SLPPhoneIds = 4
    DISPID_SLPSymbolic = 5


class DISPID_SpeechXMLRecoResult(IntFlag):
    DISPID_SRRGetXMLResult = 10
    DISPID_SRRGetXMLErrorInfo = 11


class SpeechVoiceEvents(IntFlag):
    SVEStartInputStream = 2
    SVEEndInputStream = 4
    SVEVoiceChange = 8
    SVEBookmark = 16
    SVEWordBoundary = 32
    SVEPhoneme = 64
    SVESentenceBoundary = 128
    SVEViseme = 256
    SVEAudioLevel = 512
    SVEPrivate = 32768
    SVEAllEvents = 33790


class DISPID_SpeechPhoneConverter(IntFlag):
    DISPID_SPCLangId = 1
    DISPID_SPCPhoneToId = 2
    DISPID_SPCIdToPhone = 3


class DISPID_SpeechRecoResult2(IntFlag):
    DISPID_SRRSetTextFeedback = 12


class SpeechVoicePriority(IntFlag):
    SVPNormal = 0
    SVPAlert = 1
    SVPOver = 2


class SPADAPTATIONRELEVANCE(IntFlag):
    SPAR_Unknown = 0
    SPAR_Low = 1
    SPAR_Medium = 2
    SPAR_High = 3


class SPCATEGORYTYPE(IntFlag):
    SPCT_COMMAND = 0
    SPCT_DICTATION = 1
    SPCT_SLEEP = 2
    SPCT_SUB_COMMAND = 3
    SPCT_SUB_DICTATION = 4


class SpeechStreamFileMode(IntFlag):
    SSFMOpenForRead = 0
    SSFMOpenReadWrite = 1
    SSFMCreate = 2
    SSFMCreateForWrite = 3


class SPDATAKEYLOCATION(IntFlag):
    SPDKL_DefaultLocation = 0
    SPDKL_CurrentUser = 1
    SPDKL_LocalMachine = 2
    SPDKL_CurrentConfig = 5


class DISPID_SpeechPhraseBuilder(IntFlag):
    DISPID_SPPBRestorePhraseFromMemory = 1


class DISPID_SpeechRecoResultTimes(IntFlag):
    DISPID_SRRTStreamTime = 1
    DISPID_SRRTLength = 2
    DISPID_SRRTTickCount = 3
    DISPID_SRRTOffsetFromStart = 4


class SpeechRecognizerState(IntFlag):
    SRSInactive = 0
    SRSActive = 1
    SRSActiveAlways = 2
    SRSInactiveWithPurge = 3


class DISPID_SpeechObjectToken(IntFlag):
    DISPID_SOTId = 1
    DISPID_SOTDataKey = 2
    DISPID_SOTCategory = 3
    DISPID_SOTGetDescription = 4
    DISPID_SOTSetId = 5
    DISPID_SOTGetAttribute = 6
    DISPID_SOTCreateInstance = 7
    DISPID_SOTRemove = 8
    DISPID_SOTGetStorageFileName = 9
    DISPID_SOTRemoveStorageFileName = 10
    DISPID_SOTIsUISupported = 11
    DISPID_SOTDisplayUI = 12
    DISPID_SOTMatchesAttributes = 13


class DISPID_SpeechDataKey(IntFlag):
    DISPID_SDKSetBinaryValue = 1
    DISPID_SDKGetBinaryValue = 2
    DISPID_SDKSetStringValue = 3
    DISPID_SDKGetStringValue = 4
    DISPID_SDKSetLongValue = 5
    DISPID_SDKGetlongValue = 6
    DISPID_SDKOpenKey = 7
    DISPID_SDKCreateKey = 8
    DISPID_SDKDeleteKey = 9
    DISPID_SDKDeleteValue = 10
    DISPID_SDKEnumKeys = 11
    DISPID_SDKEnumValues = 12


class DISPID_SpeechPhraseAlternate(IntFlag):
    DISPID_SPARecoResult = 1
    DISPID_SPAStartElementInResult = 2
    DISPID_SPANumberOfElementsInResult = 3
    DISPID_SPAPhraseInfo = 4
    DISPID_SPACommit = 5


class SPPARTOFSPEECH(IntFlag):
    SPPS_NotOverriden = -1
    SPPS_Unknown = 0
    SPPS_Noun = 4096
    SPPS_Verb = 8192
    SPPS_Modifier = 12288
    SPPS_Function = 16384
    SPPS_Interjection = 20480
    SPPS_Noncontent = 24576
    SPPS_LMA = 28672
    SPPS_SuppressWord = 61440


class DISPID_SpeechPhraseAlternates(IntFlag):
    DISPID_SPAsCount = 1
    DISPID_SPAsItem = 0
    DISPID_SPAs_NewEnum = -4


class DISPID_SpeechPhraseInfo(IntFlag):
    DISPID_SPILanguageId = 1
    DISPID_SPIGrammarId = 2
    DISPID_SPIStartTime = 3
    DISPID_SPIAudioStreamPosition = 4
    DISPID_SPIAudioSizeBytes = 5
    DISPID_SPIRetainedSizeBytes = 6
    DISPID_SPIAudioSizeTime = 7
    DISPID_SPIRule = 8
    DISPID_SPIProperties = 9
    DISPID_SPIElements = 10
    DISPID_SPIReplacements = 11
    DISPID_SPIEngineId = 12
    DISPID_SPIEnginePrivateData = 13
    DISPID_SPISaveToMemory = 14
    DISPID_SPIGetText = 15
    DISPID_SPIGetDisplayAttributes = 16


class DISPID_SpeechObjectTokens(IntFlag):
    DISPID_SOTsCount = 1
    DISPID_SOTsItem = 0
    DISPID_SOTs_NewEnum = -4


class SPLEXICONTYPE(IntFlag):
    eLEXTYPE_USER = 1
    eLEXTYPE_APP = 2
    eLEXTYPE_VENDORLEXICON = 4
    eLEXTYPE_LETTERTOSOUND = 8
    eLEXTYPE_MORPHOLOGY = 16
    eLEXTYPE_RESERVED4 = 32
    eLEXTYPE_USER_SHORTCUT = 64
    eLEXTYPE_RESERVED6 = 128
    eLEXTYPE_RESERVED7 = 256
    eLEXTYPE_RESERVED8 = 512
    eLEXTYPE_RESERVED9 = 1024
    eLEXTYPE_RESERVED10 = 2048
    eLEXTYPE_PRIVATE1 = 4096
    eLEXTYPE_PRIVATE2 = 8192
    eLEXTYPE_PRIVATE3 = 16384
    eLEXTYPE_PRIVATE4 = 32768
    eLEXTYPE_PRIVATE5 = 65536
    eLEXTYPE_PRIVATE6 = 131072
    eLEXTYPE_PRIVATE7 = 262144
    eLEXTYPE_PRIVATE8 = 524288
    eLEXTYPE_PRIVATE9 = 1048576
    eLEXTYPE_PRIVATE10 = 2097152
    eLEXTYPE_PRIVATE11 = 4194304
    eLEXTYPE_PRIVATE12 = 8388608
    eLEXTYPE_PRIVATE13 = 16777216
    eLEXTYPE_PRIVATE14 = 33554432
    eLEXTYPE_PRIVATE15 = 67108864
    eLEXTYPE_PRIVATE16 = 134217728
    eLEXTYPE_PRIVATE17 = 268435456
    eLEXTYPE_PRIVATE18 = 536870912
    eLEXTYPE_PRIVATE19 = 1073741824
    eLEXTYPE_PRIVATE20 = -2147483648


class DISPID_SpeechObjectTokenCategory(IntFlag):
    DISPID_SOTCId = 1
    DISPID_SOTCDefault = 2
    DISPID_SOTCSetId = 3
    DISPID_SOTCGetDataKey = 4
    DISPID_SOTCEnumerateTokens = 5


class DISPID_SpeechPhraseElement(IntFlag):
    DISPID_SPEAudioTimeOffset = 1
    DISPID_SPEAudioSizeTime = 2
    DISPID_SPEAudioStreamOffset = 3
    DISPID_SPEAudioSizeBytes = 4
    DISPID_SPERetainedStreamOffset = 5
    DISPID_SPERetainedSizeBytes = 6
    DISPID_SPEDisplayText = 7
    DISPID_SPELexicalForm = 8
    DISPID_SPEPronunciation = 9
    DISPID_SPEDisplayAttributes = 10
    DISPID_SPERequiredConfidence = 11
    DISPID_SPEActualConfidence = 12
    DISPID_SPEEngineConfidence = 13


class SPINTERFERENCE(IntFlag):
    SPINTERFERENCE_NONE = 0
    SPINTERFERENCE_NOISE = 1
    SPINTERFERENCE_NOSIGNAL = 2
    SPINTERFERENCE_TOOLOUD = 3
    SPINTERFERENCE_TOOQUIET = 4
    SPINTERFERENCE_TOOFAST = 5
    SPINTERFERENCE_TOOSLOW = 6
    SPINTERFERENCE_LATENCY_WARNING = 7
    SPINTERFERENCE_LATENCY_TRUNCATE_BEGIN = 8
    SPINTERFERENCE_LATENCY_TRUNCATE_END = 9


class DISPID_SpeechAudioFormat(IntFlag):
    DISPID_SAFType = 1
    DISPID_SAFGuid = 2
    DISPID_SAFGetWaveFormatEx = 3
    DISPID_SAFSetWaveFormatEx = 4


class DISPID_SpeechBaseStream(IntFlag):
    DISPID_SBSFormat = 1
    DISPID_SBSRead = 2
    DISPID_SBSWrite = 3
    DISPID_SBSSeek = 4


class DISPID_SpeechPhraseElements(IntFlag):
    DISPID_SPEsCount = 1
    DISPID_SPEsItem = 0
    DISPID_SPEs_NewEnum = -4


class DISPID_SpeechAudio(IntFlag):
    DISPID_SAStatus = 200
    DISPID_SABufferInfo = 201
    DISPID_SADefaultFormat = 202
    DISPID_SAVolume = 203
    DISPID_SABufferNotifySize = 204
    DISPID_SAEventHandle = 205
    DISPID_SASetState = 206


class DISPID_SpeechAudioStatus(IntFlag):
    DISPID_SASFreeBufferSpace = 1
    DISPID_SASNonBlockingIO = 2
    DISPID_SASState = 3
    DISPID_SASCurrentSeekPosition = 4
    DISPID_SASCurrentDevicePosition = 5


class DISPID_SpeechPhraseReplacement(IntFlag):
    DISPID_SPRDisplayAttributes = 1
    DISPID_SPRText = 2
    DISPID_SPRFirstElement = 3
    DISPID_SPRNumberOfElements = 4


class DISPID_SpeechMMSysAudio(IntFlag):
    DISPID_SMSADeviceId = 300
    DISPID_SMSALineId = 301
    DISPID_SMSAMMHandle = 302


class DISPID_SpeechPhraseReplacements(IntFlag):
    DISPID_SPRsCount = 1
    DISPID_SPRsItem = 0
    DISPID_SPRs_NewEnum = -4


class DISPID_SpeechPhraseProperty(IntFlag):
    DISPID_SPPName = 1
    DISPID_SPPId = 2
    DISPID_SPPValue = 3
    DISPID_SPPFirstElement = 4
    DISPID_SPPNumberOfElements = 5
    DISPID_SPPEngineConfidence = 6
    DISPID_SPPConfidence = 7
    DISPID_SPPParent = 8
    DISPID_SPPChildren = 9


class DISPID_SpeechFileStream(IntFlag):
    DISPID_SFSOpen = 100
    DISPID_SFSClose = 101


class DISPID_SpeechCustomStream(IntFlag):
    DISPID_SCSBaseStream = 100


class SpeechRunState(IntFlag):
    SRSEDone = 1
    SRSEIsSpeaking = 2


class DISPID_SpeechMemoryStream(IntFlag):
    DISPID_SMSSetData = 100
    DISPID_SMSGetData = 101


class DISPID_SpeechPhraseProperties(IntFlag):
    DISPID_SPPsCount = 1
    DISPID_SPPsItem = 0
    DISPID_SPPs_NewEnum = -4


class DISPID_SpeechAudioBufferInfo(IntFlag):
    DISPID_SABIMinNotification = 1
    DISPID_SABIBufferSize = 2
    DISPID_SABIEventBias = 3


class DISPID_SpeechPhraseRule(IntFlag):
    DISPID_SPRuleName = 1
    DISPID_SPRuleId = 2
    DISPID_SPRuleFirstElement = 3
    DISPID_SPRuleNumberOfElements = 4
    DISPID_SPRuleParent = 5
    DISPID_SPRuleChildren = 6
    DISPID_SPRuleConfidence = 7
    DISPID_SPRuleEngineConfidence = 8


class DISPID_SpeechWaveFormatEx(IntFlag):
    DISPID_SWFEFormatTag = 1
    DISPID_SWFEChannels = 2
    DISPID_SWFESamplesPerSec = 3
    DISPID_SWFEAvgBytesPerSec = 4
    DISPID_SWFEBlockAlign = 5
    DISPID_SWFEBitsPerSample = 6
    DISPID_SWFEExtraData = 7


class DISPID_SpeechLexicon(IntFlag):
    DISPID_SLGenerationId = 1
    DISPID_SLGetWords = 2
    DISPID_SLAddPronunciation = 3
    DISPID_SLAddPronunciationByPhoneIds = 4
    DISPID_SLRemovePronunciation = 5
    DISPID_SLRemovePronunciationByPhoneIds = 6
    DISPID_SLGetPronunciations = 7
    DISPID_SLGetGenerationChange = 8


class DISPID_SpeechPhraseRules(IntFlag):
    DISPID_SPRulesCount = 1
    DISPID_SPRulesItem = 0
    DISPID_SPRules_NewEnum = -4


SPSTREAMFORMATTYPE = SPWAVEFORMATTYPE
SPAUDIOSTATE = _SPAUDIOSTATE


__all__ = [
    'DISPID_SRIsUISupported',
    'SpeechPropertyNormalConfidenceThreshold',
    'DISPID_SVSInputSentenceLength', 'DISPID_SRGSetWordSequenceData',
    'SRESoundEnd', 'ISpeechAudioBufferInfo', 'DISPID_SLGenerationId',
    'SPVPRIORITY', 'DISPID_SRCEHypothesis', 'SAFT22kHz16BitStereo',
    'DISPID_SFSClose', 'DISPID_SGRSTPropertyValue',
    'DISPID_SLPsCount', 'ISpeechRecognizerStatus', 'SpShortcut',
    'SPRST_INACTIVE_WITH_PURGE', 'DISPID_SRSetPropertyNumber',
    'SPWP_UNKNOWN_WORD_PRONOUNCEABLE', 'SRAExport', 'SRCS_Disabled',
    'SPINTERFERENCE_TOOLOUD', 'DISPID_SRCEventInterests',
    'DISPID_SDKOpenKey', 'DISPID_SRGState',
    'DISPID_SRGIsPronounceable', 'DISPID_SpeechDataKey',
    'ISpRecognizer', 'SpeechCategoryAudioIn', 'SpVoice',
    'SpeechCategoryAppLexicons', 'ISpStream',
    'SpeechCategoryPhoneConverters', 'DISPID_SPPsItem', 'SPAS_RUN',
    'DISPID_SPEDisplayAttributes', 'SAFT44kHz16BitStereo',
    'eLEXTYPE_PRIVATE16', 'SpeechRecoEvents', 'DISPID_SPPChildren',
    'SPRECOSTATE', 'SPCS_ENABLED', 'SVP_1', 'SAFT44kHz8BitMono',
    'DISPID_SWFEExtraData', 'SVEAudioLevel', 'DISPID_SBSSeek',
    'SAFTCCITT_uLaw_44kHzStereo', 'DISPID_SGRSAddRuleTransition',
    'SDA_Two_Trailing_Spaces', 'SAFTText',
    '_ISpeechRecoContextEvents', 'DISPID_SPPs_NewEnum',
    'SpeechAudioFormatGUIDText', 'ISpeechLexiconWord',
    'DISPID_SABIEventBias', 'SPSSuppressWord', 'DISPID_SOTCDefault',
    'SP_VISEME_16', 'DISPID_SVSCurrentStreamNumber',
    'DISPID_SGRSTRule', 'SAFT11kHz8BitMono', 'IEnumString',
    'SDTDisplayText', 'SSFMCreateForWrite',
    'DISPID_SDKSetStringValue', 'DISPID_SLGetGenerationChange',
    'DISPIDSPTSI_SelectionOffset', 'DISPID_SVEStreamStart',
    'SPAUDIOSTATUS', 'SPRECORESULTTIMES', 'SAFT48kHz8BitStereo',
    'SpeechVoiceCategoryTTSRate', 'SPWORDPRONUNCIATION',
    'SpeechPropertyHighConfidenceThreshold', 'DISPID_SGRSTransitions',
    'DISPID_SVSInputWordLength', 'DISPID_SPRules_NewEnum',
    'SAFTCCITT_uLaw_22kHzMono', 'SAFT24kHz16BitMono', 'SPLOADOPTIONS',
    'DISPID_SLPLangId', 'eLEXTYPE_PRIVATE9', 'eLEXTYPE_RESERVED8',
    'eLEXTYPE_PRIVATE4', 'DISPID_SWFEBitsPerSample',
    'SPPHRASEELEMENT', 'SVF_Stressed',
    'DISPID_SpeechGrammarRuleStateTransitions',
    'DISPID_SPEDisplayText', 'SpeechPropertyResourceUsage',
    'SECFIgnoreWidth', 'SpeechInterference', 'SPSMF_SAPI_PROPERTIES',
    'DISPID_SAFSetWaveFormatEx', 'SVP_3', 'DISPID_SVEStreamEnd',
    'SPSHORTCUTPAIR', 'SREFalseRecognition', 'ISpeechPhraseRules',
    'DISPID_SpeechObjectTokenCategory', 'DISPID_SPIGetText',
    'DISPID_SPPName', 'SPGS_EXCLUSIVE', 'SVP_19', 'SPEI_RESERVED1',
    'SDKLDefaultLocation', 'eLEXTYPE_PRIVATE13', 'SGRSTTWord',
    'SAFTNonStandardFormat', 'SpeechDataKeyLocation',
    'SPSNotOverriden', 'SPSInterjection',
    'SpeechGrammarRuleStateTransitionType', 'SFTSREngine',
    'SP_VISEME_6', 'SREPrivate', 'DISPID_SpeechRecoResult',
    'ISpStreamFormat', 'SRSEIsSpeaking', 'SAFT12kHz8BitStereo',
    'SVSFParseSapi', 'SRAImport', 'DISPID_SRCEPropertyStringChange',
    'DISPID_SPEsCount', 'SPRECOCONTEXTSTATUS', 'SVP_6',
    'DISPID_SGRSTsItem', 'DISPID_SAVolume', 'SPLEXICONTYPE',
    'ISpMMSysAudio', 'SSTTWildcard', 'SpPhoneticAlphabetConverter',
    'SWPUnknownWordPronounceable', 'ISpNotifySink',
    'ISpeechPhraseReplacement', 'DISPID_SRGetPropertyString',
    'DISPID_SRCEFalseRecognition', 'SREHypothesis',
    'SpTextSelectionInformation', 'SGLexicalNoSpecialChars',
    'DISPID_SWFEChannels', 'DISPID_SPEAudioStreamOffset',
    'DISPID_SRRTOffsetFromStart', 'DISPID_SRRecognizer',
    'SPSTREAMFORMATTYPE', 'DISPID_SGRSTsCount', 'SDTReplacement',
    'DISPID_SVEWord', 'DISPID_SVSpeakCompleteEvent',
    'DISPID_SPRuleConfidence', 'SPPS_Function', 'DISPID_SRState',
    'SPPS_Noncontent', 'SP_VISEME_7', 'DISPID_SLPSymbolic',
    'SPXRO_Alternates_SML', 'SpeechWordType', 'SPEI_TTS_AUDIO_LEVEL',
    'SPAR_Low', 'SpeechRuleState', 'SPVOICESTATUS',
    'DISPID_SOTGetDescription', 'DISPID_SPPId', 'SpInprocRecognizer',
    'SREPhraseStart', 'SVSFPersistXML', 'SP_VISEME_2', 'SPSVerb',
    'SAFT12kHz8BitMono', 'eLEXTYPE_RESERVED4',
    'DISPID_SOTCEnumerateTokens', 'DISPID_SRGetFormat',
    'DISPID_SVSRunningState', 'SWPUnknownWordUnpronounceable',
    'SRERecognition', 'DISPID_SLWs_NewEnum', 'eLEXTYPE_PRIVATE6',
    'DISPID_SGRSTPropertyId', 'SPINTERFERENCE_TOOFAST',
    'DISPID_SLAddPronunciationByPhoneIds',
    'DISPID_SPIAudioStreamPosition', 'ISpeechPhraseInfo',
    '__MIDL___MIDL_itf_sapi_0000_0020_0001',
    'DISPIDSPTSI_SelectionLength', 'SPEI_RECO_STATE_CHANGE', 'SVP_11',
    'SVP_21', 'SpeechPartOfSpeech', 'SSTTTextBuffer',
    'SPDKL_LocalMachine', 'DISPID_SPRDisplayAttributes',
    'DISPID_SpeechPhraseReplacements', 'DISPID_SAFType',
    'DISPID_SRCCmdMaxAlternates', 'DISPID_SPEAudioSizeTime',
    'DISPID_SVWaitUntilDone', 'SLTApp', 'ISpeechPhraseReplacements',
    'Speech_Max_Word_Length', 'SpeechRunState', 'SPWORDLIST',
    'SpeechTokenKeyFiles', 'SVSFPurgeBeforeSpeak',
    'DISPID_SVEBookmark', 'SVEAllEvents',
    'SpeechCategoryRecoProfiles', 'SGLexical',
    'ISpObjectTokenCategory', 'DISPID_SDKGetBinaryValue',
    'DISPID_SOTs_NewEnum', 'DISPID_SOTCategory',
    'DISPID_SDKSetLongValue', 'SITooQuiet', 'DISPID_SRSAudioStatus',
    'SPCT_SUB_COMMAND', 'eLEXTYPE_PRIVATE2', 'SPSUnknown',
    'DISPID_SPRs_NewEnum', 'DISPID_SRGetPropertyNumber',
    'DISPID_SVPause', 'DISPID_SRGetRecognizers', 'ISpEventSource',
    'DISPID_SOTSetId', 'SECFIgnoreKanaType', 'SPINTERFERENCE',
    'DISPID_SRCPause', 'SPLO_DYNAMIC', 'SAFTGSM610_44kHzMono',
    'DISPID_SLPsItem', 'DISPID_SPEAudioTimeOffset', 'SPSModifier',
    'eLEXTYPE_PRIVATE3', 'SP_VISEME_17', 'DISPID_SVSVisemeId',
    'SPAUDIOBUFFERINFO', 'ISpRecoContext2', 'SpInProcRecoContext',
    'DISPID_SpeechGrammarRule', 'SGSExclusive', 'SPPS_Interjection',
    'SPEI_RECOGNITION', 'DISPID_SRSSupportedLanguages', 'SRATopLevel',
    'DISPID_SRRDiscardResultInfo', 'SpeechRetainedAudioOptions',
    'SRSInactiveWithPurge', 'SPWF_INPUT', 'DISPID_SRCRecognizer',
    'ISpeechDataKey', 'DISPID_SRGRecoContext',
    'DISPID_SLRemovePronunciation',
    'DISPID_SLRemovePronunciationByPhoneIds', 'SpeechVoiceEvents',
    'SVP_14', 'ISpResourceManager', 'ISpRecoGrammar2', 'SAFTDefault',
    'DISPID_SMSSetData', 'ISpRecognizer2', 'SRTSMLTimeout',
    'SAFT24kHz16BitStereo', 'DISPID_SpeechLexiconProns',
    'ISpeechLexiconPronunciations', 'SPEVENTENUM',
    'DISPID_SGRs_NewEnum', 'SVEViseme', 'eLEXTYPE_PRIVATE7',
    'SPSMF_SRGS_SEMANTICINTERPRETATION_W3C',
    'DISPID_SPRNumberOfElements', 'SASRun', 'SRAInterpreter',
    'SPEI_VOICE_CHANGE', 'SVSFParseAutodetect',
    'DISPID_SRCSetAdaptationData', 'SECFEmulateResult', 'SVPOver',
    'ISpRecoCategory', 'DISPID_SPPParent', 'SpeechLoadOption',
    'SECFDefault', 'SAFTCCITT_ALaw_8kHzMono', 'SRTExtendableParse',
    'SECHighConfidence', 'ISpStreamFormatConverter', 'SPPS_LMA',
    'SINoSignal', 'SpeechDictationTopicSpelling', 'ISpeechMMSysAudio',
    'ISpeechAudioStatus', 'DISPID_SGRSAddSpecialTransition',
    'SpeechDiscardType', 'DISPID_SRCERecognition',
    'DISPID_SpeechVoice', 'DISPID_SpeechCustomStream',
    'SWPKnownWordPronounceable', 'DISPID_SPIRule',
    'SPWT_LEXICAL_NO_SPECIAL_CHARS', 'SVSFNLPSpeakPunc',
    'SPTEXTSELECTIONINFO', 'DISPID_SPCIdToPhone',
    'DISPID_SRGSetTextSelection', 'SPINTERFERENCE_NOISE',
    'SPSMF_SRGS_SEMANTICINTERPRETATION_MS', 'SAFTNoAssignedFormat',
    'ISpeechXMLRecoResult', 'DISPID_SRGId', 'SpeechTokenShellFolder',
    'SGDisplay', 'DISPID_SPCLangId', 'DISPID_SPIReplacements',
    'DISPID_SFSOpen', 'DISPID_SPRulesItem', 'SPEI_START_INPUT_STREAM',
    'SAFT32kHz16BitMono', 'DISPID_SRCERecognitionForOtherContext',
    'SpeechStreamSeekPositionType', 'DISPID_SPISaveToMemory',
    'SVSFDefault', 'SAFTCCITT_uLaw_11kHzMono', 'eLEXTYPE_PRIVATE8',
    'SPPHRASERULE', 'DISPID_SpeechPhoneConverter',
    'DISPID_SPAStartElementInResult', 'SPVPRI_OVER',
    'DISPID_SRCState', 'DISPID_SRGCmdLoadFromProprietaryGrammar',
    'SVP_12', 'SVP_9', 'SVEWordBoundary', 'SPEI_END_SR_STREAM',
    'SDKLLocalMachine', 'SP_VISEME_4',
    'DISPID_SPRuleEngineConfidence', 'SP_VISEME_18',
    'DISPID_SRCEInterference', 'DISPID_SPRuleChildren',
    'ISpeechVoiceStatus', 'SpCompressedLexicon',
    'DISPID_SPERequiredConfidence',
    'DISPID_SPPBRestorePhraseFromMemory', 'SDTAll',
    'SPEI_RECO_OTHER_CONTEXT', 'SpeechCategoryAudioOut',
    'SREAdaptation', 'SpeechMicTraining', 'ISpNotifySource',
    'ISpeechMemoryStream', 'DISPID_SpeechGrammarRules',
    'SP_VISEME_11', 'ISpGrammarBuilder', 'DISPID_SGRsCommit',
    'ISpObjectToken', 'DISPID_SWFEBlockAlign', 'SPFM_CREATE',
    'DISPID_SRGCmdSetRuleIdState', 'DISPID_SGRSTNextState',
    'SPGRAMMARWORDTYPE', 'DISPID_SRGCmdLoadFromObject',
    'DISPID_SRCEStartStream', 'SAFTCCITT_ALaw_44kHzMono',
    'DISPID_SRCEAdaptation', 'ISpeechTextSelectionInformation',
    'SpeechDisplayAttributes', 'DISPID_SGRName',
    'ISpeechPhraseAlternates', 'SPPS_NotOverriden',
    'DISPID_SLPs_NewEnum', 'SPEI_SR_AUDIO_LEVEL',
    'SPFM_CREATE_ALWAYS', 'SPEI_UNDEFINED',
    'DISPID_SPIGetDisplayAttributes', 'eLEXTYPE_USER_SHORTCUT',
    'SpMemoryStream', 'SPRST_ACTIVE', 'SpeechRecoProfileProperties',
    'DISPID_SRAudioInputStream', 'SP_VISEME_3', 'SVP_7',
    'SP_VISEME_14', 'SGDSActiveWithAutoPause', 'SVF_Emphasis',
    'SASClosed', 'DISPID_SPERetainedStreamOffset', 'SPSMF_UPS',
    'DISPID_SRCERequestUI', 'SASPause', 'SAFTCCITT_ALaw_8kHzStereo',
    'DISPID_SpeechFileStream', 'SVEEndInputStream',
    'DISPID_SpeechPhraseReplacement', 'SAFT24kHz8BitStereo', 'STCAll',
    'SPEI_RESERVED6', 'SDA_No_Trailing_Space', 'SAFT48kHz16BitStereo',
    'SpObjectTokenCategory', 'SVSFIsXML', 'SAFT16kHz8BitStereo',
    'DISPID_SVVoice', 'ISpRecognizer3', 'DISPID_SpeechAudio',
    'SpMMAudioOut', 'DISPID_SCSBaseStream', 'SPEI_HYPOTHESIS',
    'Speech_Max_Pron_Length', 'SPBINARYGRAMMAR',
    'SPPHRASEREPLACEMENT', 'DISPID_SRGRules', 'DISPID_SGRAttributes',
    'DISPID_SRRRecoContext', 'DISPID_SpeechPhraseElements',
    'SGDSActive', 'DISPID_SRGCmdSetRuleState', 'DISPID_SRCBookmark',
    'DISPID_SVEPhoneme', 'SVSFIsNotXML', 'ISpeechRecoResultDispatch',
    'DISPID_SGRAddState', 'DISPID_SGRSTText', 'DISPID_SLGetWords',
    'SAFT16kHz16BitMono', 'DISPID_SPEAudioSizeBytes',
    'SAFT44kHz16BitMono', 'SAFT32kHz8BitStereo', 'DISPID_SPRText',
    'ISpeechPhraseProperty', 'SVP_18', 'SPEI_SR_BOOKMARK',
    'eLEXTYPE_RESERVED10', 'SRCS_Enabled', 'DISPID_SVSLastBookmarkId',
    'SVP_20', 'SREStateChange', 'DISPID_SpeechVoiceStatus',
    'ISpeechAudioFormat', 'SVSFVoiceMask', 'SPEI_TTS_BOOKMARK',
    'DISPID_SRAudioInput', 'SRADynamic', 'DISPID_SRRSpeakAudio',
    'SpeechAudioState', 'SAFTCCITT_ALaw_11kHzStereo', 'SITooFast',
    'DISPID_SGRInitialState', 'SAFTGSM610_11kHzMono', 'SPAS_STOP',
    'SpeechAudioProperties', 'SPPS_Verb', 'SPRULESTATE',
    'ISpeechLexiconWords', 'DISPID_SPPsCount',
    'SPEI_END_INPUT_STREAM', 'ISpeechGrammarRuleState',
    'SPFM_OPEN_READONLY', 'SPPS_Noun', 'ISpeechWaveFormatEx',
    'DISPID_SpeechObjectTokens', 'SpObjectToken', 'SVPNormal',
    'DISPID_SPANumberOfElementsInResult',
    'DISPID_SPEEngineConfidence', 'DISPID_SRRGetXMLErrorInfo',
    'SSFMCreate', 'SpeechLexiconType', 'SAFT11kHz8BitStereo',
    'SGRSTTWildcard', 'SREPropertyNumChange', 'DISPID_SGRSRule',
    'DISPID_SPIGrammarId', 'DISPID_SpeechAudioFormat', 'SVF_None',
    'eLEXTYPE_PRIVATE18', 'DISPID_SAFGetWaveFormatEx', 'SPPS_Unknown',
    'DISPID_SVSpeak', 'SPSHT_Unknown', 'SPCATEGORYTYPE',
    'eLEXTYPE_MORPHOLOGY', 'SPEI_START_SR_STREAM', 'SPAS_PAUSE',
    'SAFTTrueSpeech_8kHz1BitMono', 'DISPID_SLWsCount', 'SPLO_STATIC',
    'SpeechTokenContext', 'DISPID_SPRsCount', 'SPGS_DISABLED',
    'SVEVoiceChange', 'SPINTERFERENCE_LATENCY_TRUNCATE_BEGIN',
    'SREInterference', 'DISPID_SBSFormat', 'SPSHT_EMAIL',
    'ISpPhraseAlt', 'DISPID_SRGCommit', 'SAFTCCITT_uLaw_44kHzMono',
    'ISpeechObjectTokenCategory', 'SP_VISEME_9', 'DISPID_SGRSTWeight',
    'SPFM_NUM_MODES', 'DISPID_SOTId', 'SPPS_SuppressWord',
    'DISPID_SADefaultFormat', 'SpeechPropertyAdaptationOn',
    '__MIDL_IWinTypes_0009', 'ISpeechFileStream',
    'ISpeechPhraseInfoBuilder', 'SPEI_RESERVED2',
    'SPADAPTATIONRELEVANCE', 'SPEVENT', 'DISPID_SpeechRecognizer',
    'SPSHT_NotOverriden', 'ISpeechRecognizer', 'SPCT_DICTATION',
    'DISPID_SVGetVoices', 'SpeechSpecialTransitionType',
    'DISPID_SRRAudio', 'DISPID_SPPFirstElement', 'SpeechFormatType',
    'SpeechGrammarWordType', '_RemotableHandle', 'SECFNoSpecialChars',
    'SpNotifyTranslator', 'ISpeechGrammarRuleStateTransition',
    'DISPID_SVEventInterests', 'SPAR_High', 'SpeechAddRemoveWord',
    'DISPID_SGRsCommitAndSave', 'SPDKL_CurrentConfig',
    'DISPID_SPPNumberOfElements', 'DISPID_SRGCmdLoadFromMemory',
    'SAFT16kHz16BitStereo', 'DISPID_SGRClear',
    'DISPID_SpeechRecoContext', 'SDKLCurrentConfig',
    'SpeechWordPronounceable', 'SpeechVisemeType',
    'SAFT8kHz8BitStereo', 'SpeechTokenKeyAttributes',
    'DISPID_SpeechPhraseProperties',
    'DISPID_SRCAudioInInterferenceStatus', 'DISPID_SPRuleName',
    'SPAUDIOOPTIONS', 'DISPID_SOTDataKey', 'SDA_One_Trailing_Space',
    'DISPID_SRAllowAudioInputFormatChangesOnNextSet',
    'SPAO_RETAIN_AUDIO', 'SPWT_DISPLAY', 'ISpRecoContext',
    'SPCT_SUB_DICTATION', 'SPPS_Modifier', 'DISPID_SOTDisplayUI',
    'ISpeechGrammarRule', 'SAFTCCITT_uLaw_22kHzStereo',
    'eLEXTYPE_PRIVATE14', 'DISPID_SpeechMMSysAudio',
    'ISpPhoneticAlphabetSelection', 'SP_VISEME_12',
    'DISPID_SLWLangId', 'SPRST_NUM_STATES', 'DISPID_SGRSTType',
    'SAFTADPCM_44kHzMono', 'SPDATAKEYLOCATION', 'SpeechVisemeFeature',
    'DISPID_SLPPartOfSpeech', 'SWTAdded', 'STCInprocHandler',
    'SRARoot', 'DISPID_SVSLastResult', 'DISPID_SRRAlternates',
    'DISPID_SpeechPhraseInfo', 'DISPID_SASCurrentDevicePosition',
    'DISPID_SGRsItem', 'ISpPhrase', 'SRAORetainAudio', 'SPSHT_OTHER',
    'ISpeechGrammarRules', 'SpeechRecognitionType', 'SRSActive',
    'SGPronounciation', 'eLEXTYPE_PRIVATE10', 'SPEI_SOUND_END',
    'SASStop', 'SSSPTRelativeToEnd', 'SpUnCompressedLexicon',
    'DISPID_SMSGetData', 'DISPID_SRRPhraseInfo', 'SPPS_RESERVED4',
    'SPGRAMMARSTATE', 'SPRECOGNIZERSTATUS',
    'SpeechGrammarTagDictation', 'DISPID_SRRTStreamTime',
    'DISPID_SVSInputSentencePosition', 'DISPID_SASNonBlockingIO',
    'SPWP_UNKNOWN_WORD_UNPRONOUNCEABLE', 'Speech_StreamPos_Asap',
    'DISPID_SRCResume', 'DISPID_SPRuleId',
    'DISPID_SPRuleNumberOfElements', 'typelib_path', 'SREBookmark',
    'SPPS_RESERVED3', 'ISpProperties', 'SAFT22kHz16BitMono',
    'SPSHORTCUTPAIRLIST', 'SpPhoneConverter', 'DISPID_SPAs_NewEnum',
    'SAFTADPCM_8kHzStereo', 'SPEI_INTERFERENCE', 'DISPID_SRIsShared',
    'SpLexicon', 'SSSPTRelativeToStart', 'SAFT44kHz8BitStereo',
    'DISPID_SVEAudioLevel', 'SP_VISEME_20', 'DISPID_SVEEnginePrivate',
    'DISPID_SAStatus', 'DISPID_SPRuleParent', 'SpeechRuleAttributes',
    'SVP_15', 'DISPID_SVAudioOutputStream', 'DISPID_SVGetAudioInputs',
    'SpeechCategoryRecognizers', 'SpeechGrammarTagUnlimitedDictation',
    'DISPID_SOTCSetId', 'SPINTERFERENCE_LATENCY_TRUNCATE_END',
    'DISPID_SpeechWaveFormatEx', 'DISPID_SpeechRecognizerStatus',
    'SRTAutopause', 'DISPID_SRGDictationLoad', 'SP_VISEME_10',
    'IInternetSecurityManager', 'SpeechGrammarTagWildcard',
    'DISPID_SVEViseme', 'DISPID_SpeechLexiconWords',
    'DISPID_SPEsItem', '__MIDL___MIDL_itf_sapi_0000_0020_0002',
    'DISPID_SRRTimes', 'SPEI_FALSE_RECOGNITION',
    'SPSMF_SRGS_SAPIPROPERTIES', 'DISPID_SPPValue', 'SVP_2',
    'SAFTADPCM_22kHzStereo', 'SDTPronunciation', 'SREStreamEnd',
    'SAFTADPCM_11kHzMono', 'DISPID_SPELexicalForm',
    'DISPID_SRCreateRecoContext', 'SFTInput', 'SPRST_INACTIVE',
    'DISPID_SREmulateRecognition', 'DISPID_SRRSetTextFeedback',
    'DISPID_SPIEngineId', 'SPINTERFERENCE_TOOQUIET',
    'DISPID_SpeechPhraseRules', 'SPXMLRESULTOPTIONS', 'SPWORD',
    'eLEXTYPE_PRIVATE15', 'SPRS_ACTIVE_USER_DELIMITED',
    'DISPID_SPRsItem', 'SpFileStream', 'SP_VISEME_5',
    'SAFTADPCM_44kHzStereo', 'SAFTCCITT_ALaw_22kHzMono',
    'DISPID_SpeechRecoResult2', 'SRERequestUI', 'SPPROPERTYINFO',
    'DISPID_SRGCmdLoadFromResource', 'SpeechCategoryVoices',
    'DISPID_SOTGetAttribute', 'tagSTATSTG', 'ISpRecoResult',
    '_SPAUDIOSTATE', 'ISpeechPhraseElements', 'SPGS_ENABLED',
    'DISPID_SpeechGrammarRuleStateTransition',
    'IInternetSecurityMgrSite', 'SpSharedRecognizer', 'SP_VISEME_19',
    'SVSFlagsAsync', 'DISPID_SPAPhraseInfo', 'ISpeechRecoResult',
    'Speech_StreamPos_RealTime', 'DISPID_SGRsAdd',
    'DISPID_SVAllowAudioOuputFormatChangesOnNextSet',
    'SRERecoOtherContext', 'SAFTADPCM_22kHzMono',
    'SpeechPropertyLowConfidenceThreshold', 'eLEXTYPE_LETTERTOSOUND',
    'DISPID_SPERetainedSizeBytes', 'SAFT22kHz8BitMono',
    'SpeechRegistryLocalMachineRoot', 'SSTTDictation',
    'DISPID_SRGDictationSetState', 'SSSPTRelativeToCurrentPosition',
    'tagSPTEXTSELECTIONINFO', 'SVSFParseSsml', 'DISPIDSPRG',
    'SpeechEngineConfidence', 'SVP_10', 'SVP_17',
    'DISPID_SGRsDynamic', 'DISPID_SRStatus',
    'DISPID_SOTRemoveStorageFileName',
    'DISPID_SASCurrentSeekPosition', 'DISPID_SGRAddResource',
    'DISPID_SPRuleFirstElement', 'SINone', 'SAFT48kHz16BitMono',
    'DISPID_SLWType', 'DISPID_SpeechPhraseProperty',
    'DISPID_SABIBufferSize', 'SGRSTTDictation',
    'DISPID_SPRFirstElement', 'DISPID_SpeechAudioBufferInfo',
    'SPSHORTCUTTYPE', 'DISPID_SVAudioOutput', 'SP_VISEME_13',
    'SpAudioFormat', 'STCLocalServer', 'SAFT8kHz16BitStereo',
    'SDTRule', 'SPCT_COMMAND', 'IStream', 'ISpeechRecoGrammar',
    'SPINTERFERENCE_TOOSLOW', 'DISPID_SOTsItem', 'SAFT12kHz16BitMono',
    'DISPID_SOTIsUISupported', 'ISpeechPhoneConverter',
    'tagSPPROPERTYINFO', 'SGDSInactive', 'DISPID_SpeechPhraseBuilder',
    'DISPID_SRSetPropertyString', 'DISPID_SVSpeakStream',
    'SpWaveFormatEx', 'WAVEFORMATEX', 'DISPID_SpeechPhraseAlternate',
    'SPSLMA', 'DISPIDSPTSI_ActiveOffset', 'DISPID_SpeechVoiceEvent',
    'ISpeechRecoContext', 'SLOStatic', 'ISpeechLexiconPronunciation',
    'SPPHRASEPROPERTY', 'SpNullPhoneConverter',
    'DISPID_SRCRetainedAudio', 'SpeechAudioFormatType', 'DISPIDSPTSI',
    'SPEI_ADAPTATION', 'SAFT32kHz8BitMono', 'ISpeechBaseStream',
    'DISPID_SLWsItem', 'SpeechRegistryUserRoot',
    'DISPID_SVSInputWordPosition', 'DISPID_SpeechPhraseElement',
    'SPRS_INACTIVE', 'eLEXTYPE_PRIVATE12', 'Speech_Default_Weight',
    'DISPID_SRCCreateResultFromMemory', 'SAFT11kHz16BitStereo',
    'SAFT16kHz8BitMono', 'SVSFIsFilename', 'DISPID_SMSALineId',
    'SPEI_MIN_TTS', 'SAFTCCITT_ALaw_22kHzStereo',
    'DISPID_SPEActualConfidence', 'DISPID_SASetState', 'SPWORDTYPE',
    'SpMMAudioEnum', 'SAFTCCITT_uLaw_8kHzMono', 'SVEPhoneme',
    'DISPID_SGRsCount', 'SPRS_ACTIVE_WITH_AUTO_PAUSE',
    'DISPID_SpeechRecoContextEvents', 'DISPID_SRCEAudioLevel',
    'DISPID_SpeechPhraseRule', 'SDTProperty', 'SpeechGrammarState',
    'ISpXMLRecoResult', 'SPWT_PRONUNCIATION', 'SpeechBookmarkOptions',
    'SPPARTOFSPEECH', 'SPEI_RESERVED5', 'SPBO_AHEAD',
    'DISPID_SRCERecognizerStateChange', 'DISPID_SLPPhoneIds',
    'DISPID_SRGReset', 'SGRSTTEpsilon', 'DISPID_SPILanguageId',
    'SPAO_NONE', 'DISPID_SRCESoundStart', 'DISPID_SRCEEndStream',
    'SGRSTTRule', 'ISpeechLexicon',
    'SpeechPropertyComplexResponseSpeed', 'ISpAudio',
    'DISPID_SABufferNotifySize', 'DISPID_SpeechObjectToken',
    'DISPID_SPEPronunciation', 'DISPID_SRRTLength', 'SVP_8',
    'DISPID_SPIStartTime', 'DISPID_SPCPhoneToId', 'eLEXTYPE_USER',
    'DISPID_SPARecoResult', 'SAFT8kHz16BitMono', 'SpCustomStream',
    'SPEI_PROPERTY_STRING_CHANGE', 'SPEI_TTS_PRIVATE',
    'DISPID_SVSkip', 'SAFT48kHz8BitMono', 'DISPID_SRSClsidEngine',
    'SpeechTokenValueCLSID', 'SPCT_SLEEP', 'DISPID_SDKEnumValues',
    'ISpPhoneConverter', 'SPCONTEXTSTATE', 'DISPID_SPIProperties',
    'SpeechVoiceSkipTypeSentence', 'SVEStartInputStream',
    'DISPID_SRGDictationUnload', 'SVP_0', 'SPAR_Medium',
    'DISPID_SAFGuid', 'SAFT32kHz16BitStereo', 'SGSEnabled',
    'SPEI_MIN_SR', 'eLEXTYPE_PRIVATE19', 'SPVISEMES',
    'DISPID_SVDisplayUI', 'SPEI_PHONEME', 'SPXRO_SML',
    '_ISpeechVoiceEvents', 'DISPID_SpeechRecoResultTimes',
    'SpeechTokenIdUserLexicon', 'DISPID_SWFEFormatTag',
    'SAFTGSM610_8kHzMono', 'DISPID_SGRsFindRule', 'ISpeechPhraseRule',
    'SINoise', 'SpeechAudioFormatGUIDWave', 'DISPID_SPPConfidence',
    'DISPID_SRGCmdLoadFromFile', 'SpResourceManager',
    'SPSEMANTICFORMAT', 'SPEVENTSOURCEINFO',
    'DISPID_SRAllowVoiceFormatMatchingOnNextSet', 'DISPID_SVStatus',
    'DISPID_SVSPhonemeId', 'DISPID_SASFreeBufferSpace',
    'SREPropertyStringChange', 'eLEXTYPE_PRIVATE11',
    'DISPID_SVGetAudioOutputs', 'SpStreamFormatConverter',
    'DISPID_SRCEPhraseStart', 'SpMMAudioIn',
    'SAFTCCITT_ALaw_44kHzStereo', 'SPPS_RESERVED1', 'SPCS_DISABLED',
    'DISPID_SVGetProfiles', 'SpeechVoicePriority', 'SECFIgnoreCase',
    'DISPID_SVRate', 'SECNormalConfidence',
    'SpeechEmulationCompareFlags', 'SVSFNLPMask', 'SPEI_VISEME',
    'ISpeechObjectToken', 'DISPID_SLWWord', 'SPDKL_CurrentUser',
    'SAFTCCITT_uLaw_8kHzStereo', 'SPWP_KNOWN_WORD_PRONOUNCEABLE',
    'SpeechAllElements', 'DISPID_SPIEnginePrivateData', 'SGSDisabled',
    'SLODynamic', 'ISpeechPhraseProperties', 'SPVPRI_NORMAL',
    'DISPID_SRRGetXMLResult', 'DISPID_SDKCreateKey',
    'DISPID_SOTCGetDataKey', 'SAFT8kHz8BitMono', 'LONG_PTR',
    'SRTReSent', 'SPSERIALIZEDPHRASE', 'DISPID_SRRTTickCount',
    'SRESoundStart', 'ISpNotifyTranslator', 'SPEI_MAX_TTS',
    'SVEPrivate', 'SPEI_SOUND_START', 'SP_VISEME_0', 'SVP_13',
    'DISPID_SRCVoice', 'DISPID_SRCRetainedAudioFormat',
    'ISpeechResourceLoader', 'SRTStandard', 'DISPID_SpeechBaseStream',
    'DISPID_SGRSTs_NewEnum', 'ISpSerializeState', 'SITooSlow',
    'SPEI_WORD_BOUNDARY', 'DISPID_SOTRemove', 'STSF_CommonAppData',
    'DISPID_SBSRead', 'SVPAlert', 'SP_VISEME_21',
    'DISPID_SLGetPronunciations', 'SWTDeleted',
    'DISPID_SpeechLexiconPronunciation', 'DISPID_SGRSTPropertyName',
    'STSF_AppData', 'SPEI_REQUEST_UI', 'SP_VISEME_8',
    'SPSEMANTICERRORINFO', 'DISPID_SVESentenceBoundary',
    'SPINTERFERENCE_LATENCY_WARNING', 'DISPID_SVSLastBookmark',
    'SAFTExtendedAudioFormat', 'SVESentenceBoundary',
    'SPINTERFERENCE_NOSIGNAL', 'SPEI_RESERVED3',
    'DISPID_SAEventHandle', 'eLEXTYPE_PRIVATE20',
    'SpeechVoiceSpeakFlags', 'DISPID_SRRSaveToMemory',
    'DISPID_SPIRetainedSizeBytes', 'SAFTADPCM_11kHzStereo',
    'SRSActiveAlways', 'DISPID_SMSAMMHandle', 'SPBOOKMARKOPTIONS',
    'SDKLCurrentUser', 'eLEXTYPE_RESERVED7', 'SBONone',
    'SVSFParseMask', 'SDTLexicalForm', 'ISpVoice', 'SVP_5',
    'DISPID_SDKGetStringValue', 'SPINTERFERENCE_NONE',
    'DISPID_SpeechLexicon', 'DISPID_SDKSetBinaryValue',
    'DISPID_SRRAudioFormat', 'SRAONone',
    'DISPID_SRCEPropertyNumberChange', 'SPPHRASE', 'DISPID_SGRId',
    'DISPID_SVEVoiceChange', 'SPBO_NONE', 'eLEXTYPE_VENDORLEXICON',
    'eLEXTYPE_RESERVED9', 'DISPID_SOTCId', 'SpeechRecoContextState',
    'SPAS_CLOSED', 'DISPID_SRCEEnginePrivate',
    'DISPID_SLWPronunciations', 'SpeechStreamFileMode',
    'DISPID_SPIElements', 'SPFM_OPEN_READWRITE',
    'SAFT12kHz16BitStereo', 'IEnumSpObjectTokens',
    'DISPID_SpeechPhraseAlternates', 'SAFT24kHz8BitMono',
    'DISPID_SVPriority', 'DISPID_SVAlertBoundary',
    'ISpPhoneticAlphabetConverter', 'SGDSActiveUserDelimited',
    'eLEXTYPE_APP', 'SPWF_SRENGINE', 'SPVPRI_ALERT', 'SDTAudio',
    'DISPID_SRSNumberOfActiveRules', 'DISPID_SRCVoicePurgeEvent',
    'DISPID_SDKEnumKeys', 'ISpObjectWithToken',
    'DISPID_SWFEAvgBytesPerSec', 'SBOPause',
    'DISPID_SRCRequestedUIType', 'SAFTCCITT_uLaw_11kHzStereo',
    'SPEI_PROPERTY_NUM_CHANGE', 'DISPID_SRCESoundEnd', 'SpStream',
    'SPPS_RESERVED2', 'DISPID_SRProfile',
    'DISPID_SpeechXMLRecoResult', 'SSFMOpenForRead', 'SPSNoun',
    'STCRemoteServer', 'DISPID_SRSCurrentStreamNumber',
    'DISPID_SRCCreateGrammar', 'DISPID_SVSyncronousSpeakTimeout',
    'DISPID_SpeechGrammarRuleState', 'DISPID_SDKDeleteValue',
    'SPWT_LEXICAL', 'SREAllEvents', 'DISPID_SPACommit', 'ISpDataKey',
    'SAFT11kHz16BitMono', 'eLEXTYPE_PRIVATE5',
    'DISPID_SPIAudioSizeTime', 'SPAR_Unknown', 'SVEBookmark',
    'SAFTCCITT_ALaw_11kHzMono', 'SpeechAudioVolume',
    'STSF_FlagCreate', 'STSF_LocalAppData',
    'SPEI_ACTIVE_CATEGORY_CHANGED', 'SpeechEngineProperties',
    'SGRSTTTextBuffer', 'SAFTADPCM_8kHzMono',
    'DISPID_SDKGetlongValue', 'SPEI_MAX_SR', 'DISPID_SDKDeleteKey',
    'DISPID_SPAsCount', 'SPRST_ACTIVE_ALWAYS',
    'ISpeechGrammarRuleStateTransitions', 'SpeechTokenKeyUI',
    'SPEI_SR_RETAINEDAUDIO', 'DISPID_SMSADeviceId', 'eWORDTYPE_ADDED',
    'SpeechUserTraining', 'SPBO_TIME_UNITS', 'SECLowConfidence',
    'SPAUDIOSTATE', 'SPEI_SR_PRIVATE', 'SPWORDPRONOUNCEABLE',
    'SRADefaultToActive', 'ISpLexicon', 'ISpeechRecoResult2',
    'SpeechRecognizerState', 'DISPID_SOTCreateInstance',
    'ISpeechObjectTokens', 'SREStreamStart', 'SREAudioLevel',
    'SVSFUnusedFlags', 'SPDKL_DefaultLocation', 'SPSFunction',
    'SLTUser', 'ISpRecoGrammar', 'SPRS_ACTIVE',
    'ISpeechRecoResultTimes', 'SITooLoud',
    'DISPID_SLAddPronunciation', 'SPEI_SENTENCE_BOUNDARY',
    'DISPID_SRSCurrentStreamPosition', 'DISPID_SOTGetStorageFileName',
    'SAFT22kHz8BitStereo', 'DISPID_SVSLastStreamNumberQueued',
    'ISpEventSink', 'SPWORDPRONUNCIATIONLIST', 'SRSInactive',
    'DISPID_SPRulesCount', 'SDA_Consume_Leading_Spaces',
    'ISpShortcut', 'STCInprocServer', 'ISpeechPhraseAlternate',
    'DISPID_SPIAudioSizeBytes', 'SVP_4', 'SpSharedRecoContext',
    'eLEXTYPE_PRIVATE17', 'ISpeechPhraseElement', 'SPEI_PHRASE_START',
    'DISPID_SPPEngineConfidence', 'DISPID_SLPType',
    'DISPID_SRDisplayUI', 'DISPID_SABufferInfo', 'SSFMOpenReadWrite',
    'DISPID_SBSWrite', 'ISpeechVoice', 'DISPID_SRCEBookmark',
    'UINT_PTR', 'SRTEmulated', 'eWORDTYPE_DELETED', 'SRSEDone',
    'SPBO_PAUSE', 'SP_VISEME_1', 'SPSERIALIZEDRESULT',
    'DISPID_SOTMatchesAttributes', 'DISPID_SpeechAudioStatus',
    'SPFILEMODE', 'SpeechPropertyResponseSpeed',
    'DISPID_SPEs_NewEnum', 'SpPhraseInfoBuilder',
    'DISPID_SVIsUISupported', 'SDTAlternates', 'DISPID_SVResume',
    'SP_VISEME_15', 'DISPID_SOTsCount', 'SPRULE',
    'DISPID_SABIMinNotification', 'Library',
    'DISPIDSPTSI_ActiveLength', 'eLEXTYPE_RESERVED6',
    'DISPID_SpeechMemoryStream', 'eLEXTYPE_PRIVATE1', 'ISpeechAudio',
    'DISPID_SpeechLexiconWord', 'DISPID_SASState', 'SVP_16',
    'DISPID_SPAsItem', 'ISpeechCustomStream', 'SPWAVEFORMATTYPE',
    'DISPID_SGRSAddWordTransition', 'SAFTGSM610_22kHzMono',
    'DISPID_SVVolume', 'DISPID_SWFESamplesPerSec'
]

