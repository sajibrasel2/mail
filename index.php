<?php
header('Location: http://127.0.0.1:5000/' . ltrim($_SERVER['REQUEST_URI'], '/'));
exit;
?>