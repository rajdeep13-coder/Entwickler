def test_setup_logging(mocker):
    """Test that setup_logging successfully initializes the logging configuration."""
    mock_console = mocker.patch('rich.console.Console')
    mock_handler = mocker.patch('rich.logging.RichHandler')
    mocker.patch('logging.basicConfig')
    
    from logging_config import setup_logging
    
    setup_logging()
    
    mock_console.assert_called_once()
    mock_handler.assert_called_once_with(console=mock_console(), rich_tracebacks=True)
    assert mock_console.call_count == 1
    assert mock_console.return_value is not None
    logging.basicConfig.assert_called_once()
